"""DLMS/COSEM decryption adapter backed by Gurux DLMS."""

from __future__ import annotations

import contextlib
import io
import logging

from gurux_dlms.GXByteBuffer import GXByteBuffer
from gurux_dlms.GXDLMSTranslator import GXDLMSTranslator
from gurux_dlms.GXDLMSTranslatorMessage import GXDLMSTranslatorMessage

from .models import Measurement
from .obis import DlmsDataError, DlmsMetadata, extract_metadata, parse_gurux_xml

LOGGER = logging.getLogger(__name__)


class DlmsDecoder:
    """Maintain Gurux fragment state and decode Security Suite 0 pushes."""

    def __init__(self, guek: bytes) -> None:
        if len(guek) != 16:
            raise ValueError("GUEK must be exactly 16 bytes")
        self._translator = GXDLMSTranslator()
        self._translator.blockCipherKey = bytearray(guek)
        self._translator.comments = True
        self._translator.completePdu = True
        self.last_metadata = DlmsMetadata(None, None, None)

    def decode_frame(self, frame: bytes) -> Measurement | None:
        if len(frame) < 9 or frame[0] != 0x68:
            raise DlmsDataError("not a wired M-Bus long frame")
        ci_field = frame[6]
        if ci_field == 0x00:
            # A fresh first fragment supersedes any incomplete previous push.
            self._translator.clear()

        message = GXDLMSTranslatorMessage()
        message.message = GXByteBuffer(bytearray(frame))
        pdu = GXByteBuffer()
        xml_parts: list[str] = []
        try:
            # Gurux currently prints a generic security status line. Suppress it;
            # application logging deliberately never emits encrypted frame data.
            with contextlib.redirect_stdout(io.StringIO()):
                while self._translator.findNextFrame(message, pdu):
                    pdu.clear()
                    xml_parts.append(self._translator.messageToXml(message))
        except Exception as exc:
            self._translator.clear()
            raise DlmsDataError("Gurux could not decrypt the DLMS push") from exc

        xml = "".join(xml_parts)
        if not xml:
            return None
        metadata = extract_metadata(xml)
        if metadata.security_control is not None:
            if metadata.security_control & 0x03:
                raise DlmsDataError("only DLMS Security Suite 0 is supported")
            if metadata.security_control & 0x20 == 0:
                raise DlmsDataError("DLMS push is not encrypted")
        self.last_metadata = metadata
        return parse_gurux_xml(xml)
