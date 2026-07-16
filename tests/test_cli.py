import asyncio, cli


def test_parse_set():
    ns = cli.parser().parse_args(["set", "--host", "h", "--token", "t", "AC_FUN_POWER=On"])
    assert ns.cmd == "set" and ns.assignment == "AC_FUN_POWER=On"
