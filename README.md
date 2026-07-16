# Samsung AC DRC (MIM-H02 / HIH-M02)

A Home Assistant integration and standalone Python library/CLI for older Samsung
air conditioner Wi-Fi modules that speak the **DRC-1.00 protocol over TCP port
2878** — the "SmartAC" / DRC control protocol used before Samsung's SmartThings
era.

## Which modules does this support?

This targets the Samsung Wi-Fi kit sold as the **MIM-H02**, commonly mislabeled
in listings, forum posts, and even on the module's own sticker as **HIH-M02**
(the letters get transposed a lot — if you searched for either name, you're in
the right place). It works with Samsung CAC (commercial split) and ducted units
whose Wi-Fi module speaks this DRC dialect.

There are a couple of existing open-source integrations in this space, but
neither cleanly covers this module/dialect:

- [porech/samsung_ac_dplug](https://github.com/porech/samsung_ac_dplug) targets
  the newer **"DPLUG"** dialect used by different hardware.
- [SebuZet/samsungrac](https://github.com/SebuZet/samsungrac) is aging and not
  actively maintained.

This project is a from-scratch implementation specifically for the DRC-1.00 /
port 2878 dialect spoken by the MIM-H02 / HIH-M02 module.

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
talking to the module (no hostname check, no certificate chain validation,
`TLSv1` allowed). This is not an oversight — it's a hard requirement of the
hardware:

- The module presents a **self-signed, 1024-bit RSA, SHA-1 certificate** that
  "expires" in **1970** (i.e. it's already expired, permanently, from the
  factory).
- It only negotiates down to **TLS 1.0**.
- There is no CA to trust, and no way to install a valid, non-expired
  certificate on a 2013-era, end-of-life appliance — Samsung never shipped a
  mechanism for it, and the module isn't getting firmware updates.

Because of this, every known open-source implementation of this protocol
(including the projects credited below) disables verification the same way —
it's the only way to speak to this hardware at all.

This is mitigated by the fact that connections are **local-LAN only**, to a
**fixed device IP address** that you configure yourself. The integration never
connects to this module over the internet, and no data leaves your network
through this connection.

## Credits

This integration would not exist without prior reverse-engineering work on
Samsung's DRC protocol family by:

- [porech/samsung_ac_dplug](https://github.com/porech/samsung_ac_dplug)
- [SebuZet/samsungrac](https://github.com/SebuZet/samsungrac)
- [CloCkWeRX/node-samsung-airconditioner](https://github.com/CloCkWeRX/node-samsung-airconditioner)

Thank you to the authors and contributors of all three projects for figuring
out and documenting this protocol.

The bundled `ac14k_m.pem` client certificate is Samsung's own **public, shared**
certificate — extracted from Samsung's Smart Air Conditioner app and used
identically by every implementation of this protocol (including the projects
above). It is not anyone's personal secret or credential.

## About the author / Hire me

This integration was built and is maintained independently. If you need help
with home automation, integrations, or custom software work, I'm available for
hire — check out **[Vitasiti.com](https://vitasiti.com)**.

## License

MIT — see [LICENSE](LICENSE).
