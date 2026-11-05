# Extra CA certificates (optional)

Leave this folder empty unless the server's network inspects HTTPS traffic
(corporate proxy, Zscaler, etc.). Symptom in `docker compose logs etl`:

    CERTIFICATE_VERIFY_FAILED ... self-signed certificate in certificate chain

Fix: put the network's root CA certificate here as a PEM file (`*.crt` or
`*.pem`, text starting with `-----BEGIN CERTIFICATE-----`), then run
`docker compose up -d --force-recreate etl`. The folder is mounted read-only
into the etl container, which adds the certificates to its trust store at
startup. Nothing in this folder except this file is committed to git.

## On a Capgemini machine (WSL2)

If you have followed `DEVELOPMENT_WSL2.md` (section 7), the Capgemini and
Zscaler root certificates are already in your WSL trust store. Copy them here
(a copy, the originals are untouched; they are public root certificates, not
private keys):

```bash
cp /usr/local/share/ca-certificates/zscaler-root.crt \
   /usr/local/share/ca-certificates/capgemini-root.crt certs/
```

The file names depend on what you called them when you installed them. List
yours with `ls /usr/local/share/ca-certificates/` and copy every `*.crt` there
that belongs to the corporate proxy.

Then rebuild and restart the ETL container:

```bash
docker compose build etl
docker compose up -d --force-recreate etl
docker compose logs -f etl
```

A working start logs `adding 2 extra CA certificate(s)` and then fetches from
`*.aktiv-kommune.no` without `CERTIFICATE_VERIFY_FAILED`.

If you do not have the certificates in WSL yet, export them from Windows
(`certmgr.msc` -> Trusted Root Certification Authorities -> export as
"Base-64 encoded X.509 (.CER)") and save them in this folder with a `.crt`
extension. The "DER" format will not work; the file must be text starting with
`-----BEGIN CERTIFICATE-----`.
