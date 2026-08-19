from pathlib import Path
path = Path(r"c:\Users\dlwld\OneDrive\Desktop\학연생\NeSy-SMP-repro\padis\tools\run_gold_validation_expanded.py")
text = path.read_text(encoding='utf-8')
old = '    orig_rows = [r for r in rows if is_original(r[0])]\\n    new_rows = [r for r in rows if not is_original(r[0])]\\n    lines.extend(report_subset(f"Original smoke ({len(orig_rows)})", orig_rows))\\n    lines.extend(report_subset(f"New gold ({len(new_rows)})", new_rows))'
new = '    orig_rows = [r for r in rows if is_original(r[0])]\n    new_rows = [r for r in rows if not is_original(r[0])]\n    lines.extend(report_subset(f"Original smoke ({len(orig_rows)})", orig_rows))\n    lines.extend(report_subset(f"New gold ({len(new_rows)})", new_rows))'
text = text.replace(old, new)
path.write_text(text, encoding='utf-8')
print('fixed')
