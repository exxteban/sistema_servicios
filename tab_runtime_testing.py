from pathlib import Path


# El runtime de pestanas esta partido en varios includes contiguos (limite de
# 600 lineas por archivo); los tests lo leen como el unico script que arma layout.html.
TAB_RUNTIME_PARTS = (
    "part1", "open_tab", "wire_content", "part2", "bootstrap",
)


def tab_runtime_source():
    return "\n".join(
        Path(f"app/templates/layout/tab_runtime_js_{name}.html").read_text(encoding="utf-8")
        for name in TAB_RUNTIME_PARTS
    )
