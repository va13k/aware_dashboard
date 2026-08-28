"""Reading a certificate out of whatever it arrived wrapped in.

Shared because two places have to agree about it exactly: the Configurator, which
accepts one from a researcher, and the deploy, which publishes it to the phones. A
certificate one of them accepted and the other could not read would be stored as
valid and then stop every device uploading, which is the failure this whole check
exists to prevent.

What arrives is rarely just a certificate. ``docker exec`` terminates its output with
a NUL byte, a paste out of a mail client carries stray whitespace, and a managed
database often hands over a bundle holding several certificates at once. Publishing
any of that verbatim is what a client cannot parse.
"""

import base64
import binascii
import re

_CERTIFICATE = re.compile(
    r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", re.DOTALL
)


def read_certificate(pem: str) -> str:
    """Every certificate in this text, cleaned, or "" when there is nothing readable.

    A bundle is kept whole: a provider that hands over a chain expects all of it to
    be trusted, and dropping the rest would leave a client unable to build the path
    from the server's certificate to the root.
    """
    blocks = []
    for found in _CERTIFICATE.finditer(pem or ""):
        block = found.group(0)
        body = "".join(block.splitlines()[1:-1])
        try:
            if not base64.b64decode(body, validate=True):
                return ""
        except (binascii.Error, ValueError):
            return ""
        blocks.append(block)
    return "\n".join(blocks) + "\n" if blocks else ""


def valid_certificate(pem: str) -> bool:
    """Whether this holds a certificate a client could load."""
    return bool(read_certificate(pem))


def decode_certificate(encoded: str) -> str:
    """A certificate carried base64-encoded, back as the text that was encoded.

    The setup wizard hands its answers to the deploy as a ``.env`` file, where every
    line is one setting and a PEM is several. Encoding it is what lets a researcher's
    paste cross that boundary as the bytes they pasted rather than as something
    reassembled from fragments afterwards.

    Anything that is not base64 reads as nothing, which is the same answer an empty
    field gives: a study left connecting encrypted and unverified rather than one
    publishing an authority no device can load.
    """
    text = str(encoded or "").strip()
    if not text:
        return ""
    try:
        return base64.b64decode(text, validate=True).decode("utf-8", "replace")
    except (binascii.Error, ValueError):
        return ""
