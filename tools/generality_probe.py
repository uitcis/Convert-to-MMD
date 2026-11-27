"""泛化探针：用三套「从未参与调参」的骨架命名体系实测通用性。

三个测试模型（test.blend / Gley / DNF）的命名风格是：
  - mixamorig:LeftUpperArm 式（驼峰 + 冒号前缀）
  - Bip001-L-UpperArm 式（Bip 前缀 + 连字符）
  - G UpperArm L / GD Fng A1 L 式（空格分词 + 侧别后缀）

这里故意换成完全不同的四套：
  1. Unreal Mannequin：upperarm_l / lowerarm_l / calf_l（下划线 + 纯小写）
  2. Rigify DEF-：DEF-upper_arm.L / DEF-shin.L（DEForm 前缀 + 点号侧别）
  3. 纯中文：左大臂 / 左小臂 / 左小腿（无任何英文词根）
  4. 混排 + 4 指骨架：Arm_Upper_L / Leg_Lower_L + 4 根手指

只要核心骨（面板带 * 的 MMD 必需骨）解对，就说明算法靠的是
解剖语义 + 几何拓扑，而不是记住了那三个模型。
"""

import os
import sys
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import mapping_core as core  # noqa: E402


SPAN = 2.0  # 身高


def _dist(a, b):
    return sum((a[i] - b[i]) ** 2 for i in range(3)) ** 0.5


def build(definitions):
    """definitions: [(name, parent, head_xyz), ...] 身高 2.0 的骨架。

    骨长按「到第一个子骨的间距」推算；无子骨的按 0.05。
    z_pct 按 head 高度的 0~1 归一化（与主程序一致）。
    深度按父链累积。
    """
    features = {}
    parent_of = {n: p for n, p, _ in definitions}
    children_of = {n: [] for n, _, _ in definitions}
    for n, p, _ in definitions:
        if p in children_of:
            children_of[p].append(n)

    def depth_of(name):
        d, cur = 0, parent_of.get(name)
        while cur:
            d += 1
            cur = parent_of.get(cur)
        return d

    for name, parent, head in definitions:
        kids = children_of[name]
        if kids:
            head_of_child = next(h for n, p, h in definitions if n == kids[0])
            length = max(0.05, _dist(head, head_of_child))
        else:
            length = 0.05
        features[name] = SimpleNamespace(
            name=name, head=head,
            tail=(head[0], head[1], head[2] + length),
            parent=parent, children=kids, child_count=len(kids),
            depth=depth_of(name), length=length,
            z_pct=max(0.0, min(1.0, head[2] / SPAN)),
            weight_sum=0.0, weight_centroid=None,
        )
    return features


def humanoid(spine, arm, leg, head, clav, hips, root, fingers=None):
    """按给定命名拼一副人形骨架。

    spine: 躯干自下而上的名字列表（含骨盆后第一根到胸）
    arm:   (upper, lower, hand)
    leg:   (thigh, calf, foot, toe)
    clav:  锁骨名（None 表示无锁骨）
    """
    L, R = (lambda s: s + "L"), (lambda s: s + "R")
    defs = [(root, None, (0, 0, 0.0))]
    z = 0.95
    prev = root
    defs.append((hips, root, (0, 0, z)))
    prev = hips
    for i, bone in enumerate(spine):
        z += 0.16
        defs.append((bone, prev, (0, 0, z)))
        prev = bone
    chest = prev
    defs.append((head[0], chest, (0, 0, 1.70)))       # neck
    defs.append((head[1], head[0], (0, 0, 1.85)))     # head

    for side in ("Left", "Right"):
        sign = 1 if side == "Left" else -1
        base = chest if clav is None else clav
        if clav is not None:
            defs.append((clav(side), chest, (sign * 0.05, 0, 1.62)))
        u, lo, h = arm
        defs.append((u(side), base(side) if clav else chest, (sign * 0.17, 0, 1.62)))
        defs.append((lo(side), u(side), (sign * 0.41, 0, 1.62)))
        defs.append((h(side), lo(side), (sign * 0.63, 0, 1.62)))
        t, c, f, toe = leg
        defs.append((t(side), hips, (sign * 0.10, 0, 0.92)))
        defs.append((c(side), t(side), (sign * 0.10, 0, 0.50)))
        defs.append((f(side), c(side), (sign * 0.10, 0, 0.08)))
        defs.append((toe(side), f(side), (sign * 0.10, 0.12, 0.02)))
        # 手指：从掌骨末端同向平行伸出（真实手型），拇指单独偏角
        if fingers is not None:
            hand = h(side)
            count = fingers
            knuckle_x = sign * 0.70          # 指根线：掌骨末端
            seg = 0.030                      # 单节指骨长度
            for k in range(count):
                is_thumb = (k == 0)
                if is_thumb:
                    # 拇指：从掌骨侧下向斜前方伸出，与四指明显不同向
                    base = (sign * 0.66, 0.030, 1.60)
                    step = (sign * 0.020, 0.022, -0.010)
                else:
                    # 四指：根部沿 y 排开，全部沿 sign*X 平行伸出
                    fy = (k - count / 2.0) * 0.024
                    base = (knuckle_x, fy, 1.62)
                    step = (sign * seg, 0.0, 0.0)
                prev_f = hand
                head = base
                for j in range(3):
                    name = f"{side}Finger{k}_{j}"
                    defs.append((name, prev_f, head))
                    prev_f = name
                    head = (head[0] + step[0], head[1] + step[1],
                            head[2] + step[2])
    return defs


# ---------------------------------------------------------------- 四套骨架

def unreal():
    """Unreal Mannequin 风格：全小写 + 下划线 + _l/_r 后缀。"""
    def u(s): return f"upperarm_{s}"
    def lo(s): return f"lowerarm_{s}"
    def h(s): return f"hand_{s}"
    def t(s): return f"thigh_{s}"
    def c(s): return f"calf_{s}"
    def f(s): return f"foot_{s}"
    def toe(s): return f"ball_{s}"
    def clav(s): return f"clavicle_{s}"
    return humanoid(
        spine=["spine_01", "spine_02", "spine_03"],
        arm=(u, lo, h), leg=(t, c, f, toe), head=("neck_01", "head"),
        clav=clav, hips="pelvis", root="root")


def rigify():
    """Rigify DEF- 风格：DEF- 前缀 + 点号侧别 + spine.001 序号。"""
    def u(s): return f"DEF-upper_arm.{s[0]}"
    def lo(s): return f"DEF-forearm.{s[0]}"
    def h(s): return f"DEF-hand.{s[0]}"
    def t(s): return f"DEF-thigh.{s[0]}"
    def c(s): return f"DEF-shin.{s[0]}"
    def f(s): return f"DEF-foot.{s[0]}"
    def toe(s): return f"DEF-toe.{s[0]}"
    def clav(s): return f"DEF-shoulder.{s[0]}"
    return humanoid(
        spine=["DEF-spine", "DEF-spine.001", "DEF-spine.002"],
        arm=(u, lo, h), leg=(t, c, f, toe),
        head=("DEF-neck", "DEF-head"),
        clav=clav, hips="DEF-pelvis", root="DEF-root")


def chinese():
    """纯中文命名：没有任何英文词根可匹配。"""
    def u(s): return ("左大臂" if s == "Left" else "右大臂")
    def lo(s): return ("左小臂" if s == "Left" else "右小臂")
    def h(s): return ("左手" if s == "Left" else "右手")
    def t(s): return ("左大腿" if s == "Left" else "右大腿")
    def c(s): return ("左小腿" if s == "Left" else "右小腿")
    def f(s): return ("左脚" if s == "Left" else "右脚")
    def toe(s): return ("左脚趾" if s == "Left" else "右脚趾")
    def clav(s): return ("左肩" if s == "Left" else "右肩")
    return humanoid(
        spine=["腰", "上半身", "上半身2"],
        arm=(u, lo, h), leg=(t, c, f, toe),
        head=("首", "頭"),
        clav=clav, hips="下半身", root="ルート")


def mixed_four_fingers():
    """混排写法的 4 指骨架（测试手指数量不写死）。"""
    def u(s): return f"Arm_Upper_{s[0]}"
    def lo(s): return f"Arm_Lower_{s[0]}"
    def h(s): return f"Palm_{s[0]}"
    def t(s): return f"Leg_Upper_{s[0]}"
    def c(s): return f"Leg_Lower_{s[0]}"
    def f(s): return f"Leg_Foot_{s[0]}"
    def toe(s): return f"Leg_Toe_{s[0]}"
    def clav(s): return f"Collar_{s[0]}"
    return humanoid(
        spine=["Torso_A", "Torso_B", "Torso_C"],
        arm=(u, lo, h), leg=(t, c, f, toe),
        head=("Cervical", "Cranium"),
        clav=clav, hips="Waist", root="Master", fingers=4)


CORE_EXPECT = (
    "upper_body_bone", "neck_bone", "head_bone",
    "left_shoulder_bone", "left_upper_arm_bone", "left_lower_arm_bone",
    "left_hand_bone", "left_thigh_bone", "left_calf_bone",
    "left_foot_bone", "right_upper_arm_bone", "right_lower_arm_bone",
    "right_thigh_bone", "right_calf_bone", "right_foot_bone",
)


def run(label, defs):
    features = build(defs)
    stats = core.load_preset_stats()
    filled, _low, _ = core.solve(
        core.FIELD_ORDER, features, span=SPAN, diagonal=SPAN, z_min=0.0,
        up_axis=2, side_axis=0, stats=stats)
    bones = [c["bone"] for c in filled.values()]
    dup = len(bones) - len(set(bones))
    broken = 0
    for pf, cf in core.CHAIN_PAIRS:
        if pf not in filled or cf not in filled:
            continue
        pb, cb = filled[pf]["bone"], filled[cf]["bone"]
        if pb in features and cb in features:
            if not core._is_ancestor(features, pb, cb):
                broken += 1
    print(f"\n=== {label} ===")
    print(f"  填充 {len(filled)}/{len(core.FIELD_ORDER)}  重复占骨 {dup}"
          f"  链断裂 {broken}  骨总数 {len(features)}")
    for field in CORE_EXPECT:
        print(f"  {field:24s} -> {filled.get(field, {}).get('bone')}")
    return dict(filled=filled, dup=dup, broken=broken, features=features)


if __name__ == "__main__":
    for label, defs in (("Unreal Mannequin 命名", unreal()),
                        ("Rigify DEF- 命名", rigify()),
                        ("纯中文命名", chinese()),
                        ("混排 + 4 指", mixed_four_fingers())):
        run(label, defs)
