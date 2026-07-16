# Samsung AC DRC MIM-H02

A Home Assistant integration and standalone Python library/CLI for older Samsung
air conditioner Wi-Fi modules that speak the **DRC-1.00 protocol over TCP port
2878** — the "SmartAC" / DRC control protocol used before Samsung's SmartThings
era.

## Which modules does this support?

This targets the Samsung Wi-Fi kit sold as the **MIM-H02**. It works with
Samsung CAC (commercial split) and ducted units whose Wi-Fi module speaks this
DRC dialect.

Two existing open-source projects sit close to this one:

- [porech/samsung_ac_dplug](https://github.com/porech/samsung_ac_dplug) speaks
  the **"DPLUG"** dialect (greeting `DPLUG-1.x`) on the same port 2878, for
  different hardware of a similar vintage. Same transport, different
  application protocol.
- [SebuZet/samsungrac](https://github.com/SebuZet/samsungrac) does cover port
  2878, but its last commit was in March 2021 and it has a long tail of open
  issues.

The DRC-1.00 protocol layer here is written for this module's dialect (greeting
`DRC-1.00`), which is not the one porech's client speaks. The TLS setup and the
bundled Samsung certificate come from porech's MIT-licensed work — see
[Credits](#credits).

## How do I know if I have one of these modules?

From a machine on the same LAN as the module, the module should answer a TLS
connection on **TCP port 2878**, and the first line it sends after the TLS
handshake completes is a greeting containing **`DRC-1.00`**. If you can
reproduce that, this integration should work with your unit.

You can sanity-check this with `openssl` from a terminal:

```sh
openssl s_client -connect <MODULE_IP>:2878
```

(You will not get a clean handshake with default settings — see the
[security note](#a-note-on-security-tls-verification-is-disabled) below on
why this module needs an unusually permissive TLS client.)

## Finding your module's IP address

The Wi-Fi module registers itself on your network like any other DHCP client.
The easiest way to find its IP address is to check your router's **DHCP client
/ lease table** (naming varies by router: "Attached Devices," "DHCP Clients
List," "Connected Devices," etc.) and look for a device that looks like it
belongs to Samsung (vendor/MAC prefix is often a giveaway).

Once you've found it, it's strongly recommended to set up a **DHCP reservation**
(a "static lease") for that device's MAC address in your router, so its IP
address never changes. This integration is configured with a fixed IP, and the
module has no discovery/mDNS mechanism, so a moving IP will break the
integration until you update it.

## Installation via HACS

This repository is not (yet) in the default HACS store, so add it as a
**custom repository**:

1. In Home Assistant, open **HACS**.
2. Go to the three-dot menu → **Custom repositories**.
3. Add repository URL: `https://github.com/vitasiti/samsung_ac_drc`
4. Category: **Integration**.
5. Find "Samsung AC (DRC / 2878)" in HACS and install it.
6. **Restart Home Assistant.**
7. Go to **Settings → Devices & Services → Add Integration**, search for
   "Samsung AC (DRC / 2878)," and follow the setup flow described below.

## Setup

When you add the integration, you'll be asked for:

1. **The module's IP address** (see [above](#finding-your-modules-ip-address)
   for how to find it — a DHCP reservation is strongly recommended first).
2. **An authentication token**, via one of two paths:
   - **Capture a new token (guided power-cycle):** Turn the air conditioner
     **OFF**, submit the form, then turn the air conditioner back **ON within
     about 40 seconds**. The module issues a fresh token at power-on, and the
     integration captures it automatically during that window. If the window
     is missed, just retry the step.
   - **Paste an existing token:** If you already have a token (e.g. captured
     previously via the CLI, see below), you can enter it directly instead of
     power-cycling the unit.

## CLI usage

A standalone `cli.py` is included for capturing tokens, reading state, and
sending commands without Home Assistant — useful for testing or scripting.

Capture a token (same power-cycle procedure as the guided setup step):

```sh
python cli.py capture-token --host <MODULE_IP>
```

Read the current state:

```sh
python cli.py state --host <MODULE_IP> --token <TOKEN> [--duid <DUID>]
```

Send a command (example turns the unit on):

```sh
python cli.py set --host <MODULE_IP> --token <TOKEN> AC_FUN_POWER=On
```

`--duid` is optional; the client will auto-discover the device's DUID if it's
not supplied.

## A note on current temperature

The module reports the current room temperature in **degrees Fahrenheit** over
the wire, regardless of your locale. This integration converts that value to
Celsius internally before handing it to Home Assistant, and Home Assistant then
displays it using whichever unit system you have configured (°C or °F). You
don't need to do anything — this is just so the number you see makes sense if
you ever inspect the raw protocol traffic yourself.

## A note on security: TLS verification is disabled

This integration deliberately disables TLS certificate verification when
talking to the module (no hostname check, no chain validation, `TLSv1` allowed,
OpenSSL security level 0). That is not an oversight. The following was measured
against a real MIM-H02, and every part of it constrains what a client can do.

**The certificate the module presents:**

```
subject      : emailAddress=moweon.lee@samsung.com, CN=a287848,
               OU=Digital Applicance, O=Samsung Electronics, L=Suwon, C=KR
issuer       : (identical — self-signed)
sig algorithm: sha1WithRSAEncryption
key          : RSA 1024 bits
not before   : 2026-07-16 09:11:07 UTC   <- the moment the unit was powered on
not after    : 2026-08-16 09:11:07 UTC
```

- It is **self-signed**, so there is no CA to validate it against.
- It is **regenerated at every boot**, valid for one month from power-on. The
  certificate above was minted seconds after the module started. So it cannot
  be pinned either: reboot the AC and the fingerprint changes.
- **1024-bit RSA with a SHA-1 signature.** Modern OpenSSL refuses both at its
  default security level, which is why `@SECLEVEL=0` is required.
- It is issued to `CN=a287848`, which will never match the module's IP address,
  so a hostname check cannot pass.

**The transport:**

- The module speaks **TLS 1.0 and nothing else**. TLS 1.1, 1.2 and 1.3 are all
  refused outright (`unsupported protocol`).
- Its **Diffie-Hellman parameters are broken**: offering DH ciphers fails the
  handshake with `bad dh value`. This is why the cipher string excludes them
  (`HIGH:!DH:!aNULL:@SECLEVEL=0`) — `!DH` is load-bearing, not decoration.

There is no way to fix any of this from the outside: Samsung never shipped a
mechanism for installing a certificate on these modules, and they stopped
receiving firmware updates long ago.

Other implementations handle this differently, and it is worth knowing that
disabling verification is a choice rather than the only option.
[samsungrac](https://github.com/SebuZet/samsungrac), for instance, defaults to
`CERT_REQUIRED` and verifies the module against the CA chain bundled inside
`ac14k_m.pem` — that file contains not just the client certificate but a chain
up to a Samsung root. That approach cannot work on the unit measured above,
whose certificate is self-signed and chains to nothing, but it may work on
other hardware in this family.

The exposure here is bounded: connections are **local-LAN only**, to a **fixed
IP address you configure yourself**. The integration never talks to this module
over the internet, and no data leaves your network through this connection. An
attacker already positioned on your LAN could impersonate the module — but the
hardware offers nothing that would let a client detect it.

## Credits

This integration would not exist without prior reverse-engineering work on
Samsung's DRC protocol family by:

- [porech/samsung_ac_dplug](https://github.com/porech/samsung_ac_dplug) and its
  [pysamsung-dplug](https://github.com/porech/pysamsung-dplug) library
- [SebuZet/samsungrac](https://github.com/SebuZet/samsungrac)
- [CloCkWeRX/node-samsung-airconditioner](https://github.com/CloCkWeRX/node-samsung-airconditioner)

Thank you to the authors and contributors of all three projects for figuring
out and documenting this protocol.

**Code from porech.** `build_ssl_context()` in `drc_client.py` is taken from
porech's `pysamsung-dplug`, which is MIT licensed — see [NOTICE](NOTICE). Both
modules need the same unusual TLS client, and there is no point in pretending
that was arrived at independently. The DRC-1.00 protocol layer is written for
this module's dialect, which is a different one.

**The bundled `ac14k_m.pem`** is Samsung's own client certificate, shipped
inside Samsung's air conditioner app. It is shared, not per-device: the same
file is byte-for-byte identical across this project, `pysamsung-dplug`,
`samsungrac`, and `homebridge-samsung-airconditioner`.

It does contain an unencrypted RSA-2048 private key, so it is a credential in
the literal sense — but it is Samsung's, published years ago, and identical on
every install. It is **not a per-user or per-device secret**, and nothing about
your AC or network is derivable from it. (The frequently repeated claim that it
was extracted from the app is plausible and universally assumed, but I have not
found a primary source demonstrating it.)

## About the author / Hire me

This integration was built and is maintained independently. If you need help
with home automation, integrations, or custom software work, I'm available for
hire — check out **[Vitasiti.com](https://vitasiti.com)**.

## License

MIT — see [LICENSE](LICENSE).
