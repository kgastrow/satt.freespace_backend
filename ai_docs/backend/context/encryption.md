# Field-Level Encryption

## Overview
Sensitive data (API keys, passwords, credentials) is encrypted at rest using Fernet symmetric encryption (AES-128-CBC with HMAC-SHA256).

## Key Configuration
Configure in `config.json`:
```json
{
  "encryption": {
    "key": "base64-encoded-fernet-key",
    "key_previous": "old-key-for-rotation"
  }
}
```

**CRITICAL**: `ENCRYPTION_KEY` is required in production. Missing key raises `RuntimeError`. JWT-derived fallback is only allowed when `TESTING=true`.

## Usage
```python
from src.core.encryption import encrypt_field, decrypt_field

encrypted = encrypt_field("secret_value")  # Returns base64 string
decrypted = decrypt_field(encrypted)       # Returns plaintext
```

Decryption tries keys in order: primary -> previous -> fallback, enabling seamless rotation.

## Auto-Encrypted SystemConfig Keys
Keys containing these patterns (case-insensitive) are encrypted on save, masked on read:
`.api_key`, `.apikey`, `.password`, `.pass`, `.secret`, `.token`, `.credential`, `.private_key`, `.auth_key`, `.client_secret`, `.access_key`, `.secret_key`, `.license_key`

## Key Rotation
```bash
# From app/backend/
python scripts/rotate_encryption_keys.py --generate-key  # Generate new key
python scripts/rotate_encryption_keys.py --check-keys    # Verify key config
python scripts/rotate_encryption_keys.py --dry-run       # Preview changes
python scripts/rotate_encryption_keys.py                 # Re-encrypt all data
```

Process: Generate new key -> Move current to `key_previous` -> Set new as `key` -> Run rotation -> Verify -> Remove `key_previous`
