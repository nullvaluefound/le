# le APT archive public key

Primary fingerprint: `9ECD6CC083C1EE9EF8EDD26240167FE47E9E1C26`

Identity: `le APT Archive (nullvaluefound/le) <jpmak98@gmail.com>`.
The Ed25519 signing key expires on **2029-11-06 UTC**. Rotate or renew the key
before expiry, following `docs/DISTRIBUTION.md`.

`le-archive-keyring.gpg` contains only the public key. The private key and
passphrase belong only in the protected `apt-release` GitHub environment and
the encrypted recovery backup outside this repository. No private material or
revocation certificate is published here.

Verify this fingerprint through an independently trusted channel before adding
the archive to a client. The bootstrap uses a dedicated `Signed-By` keyring.
