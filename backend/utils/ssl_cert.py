import os
import socket
import ipaddress
from datetime import datetime, timedelta, timezone
from pathlib import Path

def get_all_local_ips() -> list[str]:
    """Discovers all active local IPv4 LAN addresses (Wi-Fi, Ethernet, Hotspot)."""
    discovered = []
    
    # 1. Preferred route via dummy UDP socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 1))
        outbound = s.getsockname()[0]
        if outbound and not outbound.startswith('127.'):
            discovered.append(outbound)
        s.close()
    except Exception:
        pass

    # 2. Hostname resolution enumeration
    try:
        hostname = socket.gethostname()
        _, _, host_ips = socket.gethostbyname_ex(hostname)
        for ip in host_ips:
            if ip and not ip.startswith('127.') and ip not in discovered:
                discovered.append(ip)
    except Exception:
        pass

    # 3. Fallback to 127.0.0.1 if nothing found
    if not discovered:
        discovered.append('127.0.0.1')
        
    return discovered

def get_outbound_ip() -> str:
    """Detects primary outbound local LAN IP address."""
    ips = get_all_local_ips()
    return ips[0] if ips else "127.0.0.1"

def ensure_ssl_certificates(base_dir: Path = None, force_regenerate: bool = False) -> tuple[str, str]:
    """
    Ensures self-signed SSL certificate and private key exist for HTTPS.
    Automatically regenerates certs/cert.pem and certs/key.pem if:
      - Either file is missing
      - force_regenerate is True
      - The current active LAN IP(s) are not present in the certificate SAN list
      - The certificate has expired
    Returns (cert_path, key_path).
    """
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent.parent.parent
    
    certs_dir = base_dir / "certs"
    certs_dir.mkdir(parents=True, exist_ok=True)
    
    cert_path = certs_dir / "cert.pem"
    key_path = certs_dir / "key.pem"
    
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    active_ips = get_all_local_ips()
    primary_ip = active_ips[0]

    # Check existing certificate validity and SAN coverage
    needs_generation = force_regenerate or not cert_path.exists() or not key_path.exists()
    
    if not needs_generation:
        try:
            cert_bytes = cert_path.read_bytes()
            existing_cert = x509.load_pem_x509_certificate(cert_bytes)
            
            # Check expiration
            now = datetime.now(timezone.utc)
            if existing_cert.not_valid_after_utc < now:
                needs_generation = True
            else:
                # Check if all active IPs are covered in SAN
                try:
                    san_ext = existing_cert.extensions.get_extension_for_oid(
                        x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
                    )
                    existing_san_ips = {
                        str(item.value) for item in san_ext.value
                        if isinstance(item, x509.IPAddress)
                    }
                    for ip_str in active_ips:
                        if ip_str != '127.0.0.1' and ip_str not in existing_san_ips:
                            needs_generation = True
                            break
                except x509.ExtensionNotFound:
                    needs_generation = True
        except Exception:
            needs_generation = True

    if not needs_generation:
        return str(cert_path), str(key_path)

    # Generate fresh self-signed certificate with all active IPs
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, f"SENTINEL-AI Recon Server ({primary_ip})"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SENTINEL-AI Tactical Recon"),
    ])

    san_list: list[x509.GeneralName] = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
    ]
    try:
        san_list.append(x509.DNSName(socket.gethostname()))
    except Exception:
        pass

    for ip_str in active_ips:
        try:
            san_ip = ipaddress.IPv4Address(ip_str)
            if san_ip not in [item.value for item in san_list if isinstance(item, x509.IPAddress)]:
                san_list.append(x509.IPAddress(san_ip))
        except Exception:
            pass

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName(san_list), critical=False)
        .sign(key, hashes.SHA256())
    )

    with open(key_path, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))

    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    return str(cert_path), str(key_path)

