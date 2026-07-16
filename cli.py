"""Standalone CLI for Samsung DRC AC modules."""
import argparse, asyncio, sys
from custom_components.samsung_ac_drc.drc_client import SamsungDrcClient
from custom_components.samsung_ac_drc import mappings

def parser():
    p = argparse.ArgumentParser(prog="samsung-ac-drc")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("capture-token", "state", "set"):
        sp = sub.add_parser(name)
        sp.add_argument("--host", required=True)
        sp.add_argument("--token")
        sp.add_argument("--duid")
        if name == "set": sp.add_argument("assignment")
        if name == "capture-token": sp.add_argument("--timeout", type=float, default=120)
    return p

async def _run(ns):
    if ns.cmd == "capture-token":
        c = SamsungDrcClient(ns.host)
        print("Turn the AC OFF, press Enter, then turn it ON within the window.")
        tok = await c.get_token(power_on_timeout=ns.timeout); print("TOKEN:", tok); await c.close()
    else:
        c = SamsungDrcClient(ns.host, token=ns.token, duid=ns.duid)
        if ns.cmd == "state":
            for k, v in mappings.state_to_ha(await c.get_state()).items(): print(f"{k}: {v}")
        else:
            k, v = ns.assignment.split("=", 1); await c.set_attr(k, v); print("ok")
        await c.close()

def main(): asyncio.run(_run(parser().parse_args()))
if __name__ == "__main__": main()
