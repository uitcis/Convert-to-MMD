"""对比两次 scan_all_models.py 的快照，检查有没有回退。

用法：
    python dev/compare_scan.py dev/scan_snapshot.txt dev/scan_new.txt

按 (文件, 骨架名) 配对，输出：
  - 覆盖情况（新增 / 消失 / 共同）
  - filled、solid 的升降分布
  - 链断裂、核心骨合计
  - 逐条列出 filled 或 solid 变差的骨架（这是必须解释清楚的）
"""
import collections
import sys


def load(path):
    rows = {}
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 10 or parts[0] != "R":
                continue
            key = (parts[1], parts[2])
            rows[key] = {
                "bones": int(parts[3] or 0),
                "filled": int(parts[4] or 0),
                "solid": int(parts[5] or 0),
                "broken": int(parts[6] or 0),
                "core": int(parts[7] or 0),
            }
    return rows


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    old = load(sys.argv[1])
    new = load(sys.argv[2])
    common = sorted(set(old) & set(new))
    print("旧快照 %d 条，新快照 %d 条，共同 %d 条" % (len(old), len(new), len(common)))
    only_old = set(old) - set(new)
    only_new = set(new) - set(old)
    if only_old:
        print("仅旧快照有 %d 条：%s" % (len(only_old), list(only_old)[:3]))
    if only_new:
        print("仅新快照有 %d 条" % len(only_new))

    delta_filled = collections.Counter()
    delta_solid = collections.Counter()
    worse = []
    better = []
    for key in common:
        a, b = old[key], new[key]
        df = b["filled"] - a["filled"]
        ds = b["solid"] - a["solid"]
        delta_filled[df] += 1
        delta_solid[ds] += 1
        if df < 0 or ds < 0:
            worse.append((key, a, b))
        elif df > 0 or ds > 0:
            better.append((key, a, b))

    total_old = sum(old[k]["filled"] for k in common)
    total_new = sum(new[k]["filled"] for k in common)
    solid_old = sum(old[k]["solid"] for k in common)
    solid_new = sum(new[k]["solid"] for k in common)
    broken_old = sum(old[k]["broken"] for k in common)
    broken_new = sum(new[k]["broken"] for k in common)
    core_old = sum(1 for k in common if old[k]["core"] > 0)
    core_new = sum(1 for k in common if new[k]["core"] > 0)

    print("\n合计 filled %d -> %d （%+d）" % (total_old, total_new, total_new - total_old))
    print("合计 solid  %d -> %d （%+d）" % (solid_old, solid_new, solid_new - solid_old))
    print("链断裂合计 %d -> %d （%+d）" % (broken_old, broken_new,
                                       broken_new - broken_old))
    print("核心骨非空骨架 %d -> %d" % (core_old, core_new))
    print("filled 变化分布 %s" % dict(sorted(delta_filled.items())))
    print("solid  变化分布 %s" % dict(sorted(delta_solid.items())))

    if better:
        print("\n变好 %d 条：" % len(better))
        for key, a, b in better[:20]:
            print("  + %s | %s | %d/%d -> %d/%d" % (
                key[0], key[1], a["filled"], a["solid"],
                b["filled"], b["solid"]))
    if worse:
        print("\n变差 %d 条（必须逐条解释）：" % len(worse))
        for key, a, b in worse:
            print("  - %s | %s | %d/%d -> %d/%d  broken %d->%d" % (
                key[0], key[1], a["filled"], a["solid"],
                b["filled"], b["solid"], a["broken"], b["broken"]))
    else:
        print("\n无任何骨架变差。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
