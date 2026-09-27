from __future__ import annotations

from netznoe_p1_reader.mbus import MBusFramer

from .helpers import mbus_frame

FRAME_A = mbus_frame(b"\x53\xff\x11\x01\x67hello")
FRAME_B = mbus_frame(b"\x53\xff\x11\x01\x67world")


def test_fragmented_frame() -> None:
    parser = MBusFramer()
    assert parser.feed(FRAME_A[:3]) == []
    assert parser.feed(FRAME_A[3:8]) == []
    assert parser.feed(FRAME_A[8:]) == [FRAME_A]


def test_multiple_frames_in_one_chunk() -> None:
    assert MBusFramer().feed(FRAME_A + FRAME_B) == [FRAME_A, FRAME_B]


def test_discards_noise_before_frame() -> None:
    parser = MBusFramer()
    assert parser.feed(b"noise\x00\xff" + FRAME_A) == [FRAME_A]
    assert parser.stats.discarded_bytes == 7


def test_invalid_duplicate_length_recovers() -> None:
    parser = MBusFramer()
    broken = b"\x68\x0a\x09\x68garbage"
    assert parser.feed(broken + FRAME_A) == [FRAME_A]
    assert parser.stats.invalid_headers >= 1


def test_bad_checksum_is_rejected() -> None:
    parser = MBusFramer()
    broken = bytearray(FRAME_A)
    broken[-2] ^= 0x01
    assert parser.feed(bytes(broken)) == []
    assert parser.stats.invalid_checksums == 1


def test_missing_or_wrong_end_byte_is_rejected() -> None:
    parser = MBusFramer()
    assert parser.feed(FRAME_A[:-1]) == []
    parser.on_timeout()
    assert parser.stats.timed_out_frames == 1

    broken = bytearray(FRAME_A)
    broken[-1] = 0
    assert parser.feed(bytes(broken)) == []
    assert parser.stats.invalid_end_bytes == 1


def test_recovers_after_corrupt_frame() -> None:
    parser = MBusFramer()
    broken = bytearray(FRAME_A)
    broken[-2] ^= 0x80
    assert parser.feed(bytes(broken) + FRAME_B) == [FRAME_B]


def test_complete_frame_behind_bogus_partial_header_is_not_stalled() -> None:
    parser = MBusFramer()
    bogus = b"\x68\xfa\xfa\x68junk"
    assert parser.feed(bogus + FRAME_A) == [FRAME_A]
