import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey


def base64_encode_str(text: str) -> str:
    """Encode a string to base64 format.

    Args:
        text: The string to encode.

    Returns:
        Base64-encoded string.

    Examples:
        >>> base64_encode_str("hello")
        'aGVsbG8='
    """
    return base64.b64encode(text.encode()).decode()


def name_prefix(name: str) -> str:
    """Extract the prefix from a dotted name.

    # TODO: refactor to a more huristic approach.

    Args:
        name: The name containing dots (e.g., "file.txt", "archive.tar.gz").

    Returns:
        The portion before the first dot. If no dot exists, returns the entire name.

    Examples:
        >>> name_prefix("file.txt")
        'file'
        >>> name_prefix("archive.tar.gz")
        'archive'
        >>> name_prefix("noextension")
        'noextension'
    """
    return name.split(".")[0]


def authorized_key(private_key_path: str) -> str:
    """Generate an SSH authorized_keys entry from a private key file.

    Args:
        private_key_path: Path to the RSA private key file.

    Returns:
        Formatted SSH authorized_keys entry (ssh-rsa <base64> root@exec1.rdocloud).

    Examples:
        >>> authorized_key("/path/to/id_rsa")
        'ssh-rsa AAAAB3NzaC1yc2E... root@exec1.rdocloud'
    """
    return f"ssh-rsa {private_to_public_key(key=private_key_path)} root@exec1.rdocloud"


def private_to_public_key(key: str) -> str:
    """Convert an RSA private key to its base64-encoded public key.

    Args:
        key: Path to the RSA private key file.

    Returns:
        Base64-encoded public key string.
    """
    with open(key, "rb") as key_file:
        private_key = serialization.load_pem_private_key(
            data=key_file.read(),
            password=None,
        )

    if not isinstance(private_key, RSAPrivateKey):
        raise ValueError(f"Expected RSA key, got {type(private_key).__name__}")

    public_key = private_key.public_key()
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    )

    # public_bytes is in format: "ssh-rsa AAAA... comment"
    # We need just the base64 part (second field)
    parts = public_bytes.decode().split()
    if len(parts) >= 2:
        return parts[1]
    return public_bytes.decode()
