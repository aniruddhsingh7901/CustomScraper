#!/usr/bin/env python3
import pkgutil
import importlib
import inspect
import pathlib
import datetime as dt


def _is_public(name: str) -> bool:
    return not name.startswith("_")


def _walk_package_modules(pkg) -> list[str]:
    """Return a list of fully-qualified submodule names for a package."""
    names = [pkg.__name__]
    if hasattr(pkg, "__path__"):
        for mod_info in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + "."):
            names.append(mod_info.name)
    return names


def _gather_asyncpraw_api():
    """Import asyncpraw and introspect public modules, classes, methods, functions."""
    try:
        asyncpraw = importlib.import_module("asyncpraw")
    except Exception as e:
        raise RuntimeError(f"Failed to import asyncpraw: {e!r}")

    modules = []
    failed_imports = []

    for modname in _walk_package_modules(asyncpraw):
        try:
            mod = importlib.import_module(modname)
            modules.append(mod)
        except Exception as e:
            failed_imports.append((modname, repr(e)))

    totals = {
        "public_classes": 0,
        "public_class_methods": 0,
        "public_class_properties": 0,
        "public_module_functions": 0,
    }

    details = []
    seen_classes = set()  # (qualname, module)

    for mod in modules:
        mod_entry = {"module": mod.__name__, "functions": [], "classes": []}

        # Module-level public functions/coroutines
        try:
            for name, obj in inspect.getmembers(mod):
                if not _is_public(name):
                    continue
                if inspect.isfunction(obj) or inspect.iscoroutinefunction(obj):
                    mod_entry["functions"].append(name)
        except Exception:
            pass

        totals["public_module_functions"] += len(mod_entry["functions"])

        # Classes actually defined in this module (avoid re-exports/aliases)
        try:
            for name, obj in inspect.getmembers(mod, inspect.isclass):
                if not _is_public(name):
                    continue
                if getattr(obj, "__module__", "") != mod.__name__:
                    continue

                key = (obj.__qualname__, obj.__module__)
                if key in seen_classes:
                    continue
                seen_classes.add(key)

                methods = set()
                properties = set()

                # Collect public methods/properties
                for mname, mobj in inspect.getmembers(obj):
                    if not _is_public(mname):
                        continue
                    try:
                        if isinstance(mobj, property):
                            properties.add(mname)
                        elif (
                            inspect.isfunction(mobj)
                            or inspect.ismethod(mobj)
                            or inspect.iscoroutinefunction(mobj)
                        ):
                            methods.add(mname)
                    except Exception:
                        continue

                mod_entry["classes"].append(
                    {
                        "name": name,
                        "methods": sorted(methods),
                        "properties": sorted(properties),
                    }
                )

                totals["public_classes"] += 1
                totals["public_class_methods"] += len(methods)
                totals["public_class_properties"] += len(properties)
        except Exception:
            pass

        details.append(mod_entry)

    report = {
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "package": "asyncpraw",
        "version": getattr(importlib.import_module("asyncpraw"), "__version__", "unknown"),
        "module_count": len(modules),
        "failed_imports": failed_imports,
    }

    return report, totals, details


def _write_markdown(output_path: str) -> str:
    report, totals, details = _gather_asyncpraw_api()

    lines = []
    lines.append("# asyncpraw API report (introspected)")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at']}")
    lines.append(f"- Package: {report['package']} version: {report.get('version', 'unknown')}")
    lines.append(f"- Modules scanned: {report['module_count']}")
    if report["failed_imports"]:
        lines.append(f"- Failed imports: {len(report['failed_imports'])}")
        for name, err in report["failed_imports"]:
            lines.append(f"  - {name}: {err}")
    lines.append("")
    lines.append("## Totals")
    lines.append(f"- Public classes: {totals['public_classes']}")
    lines.append(f"- Public class methods: {totals['public_class_methods']}")
    lines.append(f"- Public class properties: {totals['public_class_properties']}")
    lines.append(f"- Public module-level functions: {totals['public_module_functions']}")
    lines.append("")

    for mod_entry in sorted(details, key=lambda e: e["module"]):
        lines.append(f"### Module: {mod_entry['module']}")
        if mod_entry["functions"]:
            lines.append("")
            lines.append("Functions")
            for fn in sorted(mod_entry["functions"]):
                lines.append(f"- {fn}")
        if mod_entry["classes"]:
            for cls in sorted(mod_entry["classes"], key=lambda c: c["name"]):
                lines.append("")
                lines.append(f"Class {cls['name']}")
                if cls["properties"]:
                    lines.append("  Properties:")
                    for p in cls["properties"]:
                        lines.append(f"  - {p}")
                if cls["methods"]:
                    lines.append("  Methods:")
                    for m in cls["methods"]:
                        lines.append(f"  - {m}")
        lines.append("")

    path = pathlib.Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def main():
    out = _write_markdown("docs/asyncpraw_api_report.md")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
