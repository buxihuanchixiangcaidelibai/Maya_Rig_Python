import json
import math
import sys

import maya.standalone
maya.standalone.initialize(name="python")
import maya.cmds as cmds

SCENE = r"C:\Users\haoguoli\Desktop\shengzi\shengzi_Rig_FIXED.ma"
cmds.file(SCENE, o=True, f=True, prompt=False)

geo = "ROPE_GEO"
curve = "ROPE_DRIVER_CRV"
bbox0 = cmds.exactWorldBoundingBox(geo)
lengths = [bbox0[i+3]-bbox0[i] for i in range(3)]
axis = lengths.index(max(lengths))
cross = [i for i in range(3) if i != axis]
major = lengths[axis]

def refresh():
    cmds.dgdirty(allPlugs=True)
    cmds.refresh(force=True)

def p(i):
    return cmds.pointPosition(curve + ".cv[%d]" % i, w=True)

def d(a,b):
    return math.sqrt(sum((a[k]-b[k])**2 for k in range(3)))

def transform_test(node, attr, value, cv):
    old = cmds.getAttr(node + "." + attr)
    before = p(cv)
    cmds.setAttr(node + "." + attr, value)
    refresh()
    delta = d(before, p(cv))
    cmds.setAttr(node + "." + attr, old)
    refresh()
    return delta

cross_t = "t" + "xyz"[cross[0]]
rot_attr = "r" + "xyz"[cross[1]]
axis_t = "t" + "xyz"[axis]

tests = {}
tests["mainIK"] = transform_test("MAIN_IK_05_CTRL", cross_t, major*.055, 8)
tests["secondaryIK"] = transform_test("SECONDARY_IK_04_CTRL", cross_t, -major*.035, 7)
tests["sculpt"] = transform_test("SCULPT_09_CTRL", cross_t, major*.018, 8)
tests["fk"] = transform_test("FK_04_CTRL", rot_attr, 20.0, 10)
tests["knotPivot"] = transform_test("KNOT_PIVOT_02_CTRL", cross_t, major*.018, 3)
tests["lassoOpen"] = transform_test("LASSO_GLOBAL_CTRL", "loopOpen", major*.022, 14)
tests["lassoDrop"] = transform_test("LASSO_GLOBAL_CTRL", "sag", -major*.018, 16)

curve_info = "ROPE_ARCLENGTH_CIF"
arc0 = cmds.getAttr(curve_info + ".arcLength")
old = cmds.getAttr("MAIN_IK_09_CTRL." + axis_t)
cmds.setAttr("MAIN_IK_09_CTRL." + axis_t, old + major*.10)
refresh()
tests["stretchRatio"] = cmds.getAttr(curve_info + ".arcLength") / arc0
cmds.setAttr("MAIN_IK_09_CTRL." + axis_t, old)
refresh()

# Twist must propagate through the spline IK joint chain.
mid_joint = "ROPE_BIND_021_JNT"
m0 = cmds.xform(mid_joint, q=True, ws=True, m=True)
rot_axis_attr = "r" + "xyz"[axis]
old_rot = cmds.getAttr("MAIN_IK_09_CTRL." + rot_axis_attr)
cmds.setAttr("MAIN_IK_09_CTRL." + rot_axis_attr, old_rot + 90.0)
refresh()
m1 = cmds.xform(mid_joint, q=True, ws=True, m=True)
tests["twistMatrixDelta"] = max(abs(m1[i]-m0[i]) for i in range(16))
cmds.setAttr("MAIN_IK_09_CTRL." + rot_axis_attr, old_rot)
refresh()

# Secondary follow choices and manual blend are live.
sec = "SECONDARY_IK_04_CTRL"
pc = "SECONDARY_IK_04_CTRL_ZERO_FOLLOW_PC"
aliases = cmds.parentConstraint(pc, q=True, wal=True) if cmds.objExists(pc) else []
follow_values = []
for mode in range(4):
    cmds.setAttr(sec + ".useCustomFollow", 0)
    cmds.setAttr(sec + ".followMode", mode)
    refresh()
    follow_values.append([cmds.getAttr(pc + "." + a) for a in aliases])
cmds.setAttr(sec + ".followMode", 0)
cmds.setAttr(sec + ".useCustomFollow", 1)
cmds.setAttr(sec + ".followLeft", .2)
cmds.setAttr(sec + ".followRight", .7)
cmds.setAttr(sec + ".followWorld", .1)
refresh()
manual_values = [cmds.getAttr(pc + "." + a) for a in aliases]
cmds.setAttr(sec + ".useCustomFollow", 0)
cmds.setAttr(sec + ".followLeft", .5)
cmds.setAttr(sec + ".followRight", .5)
cmds.setAttr(sec + ".followWorld", 0)
refresh()

bbox1 = cmds.exactWorldBoundingBox(geo)
skin_nodes = cmds.ls(type="skinCluster") or []
mesh_skins = [s for s in skin_nodes if geo in (cmds.skinCluster(s,q=True,g=True) or []) or "ROPE_GEOShape" in (cmds.skinCluster(s,q=True,g=True) or [])]
mesh_skin = "ROPE_SKINCLUSTER" if cmds.objExists("ROPE_SKINCLUSTER") else (mesh_skins[0] if mesh_skins else None)
infs = cmds.skinCluster(mesh_skin,q=True,inf=True) if mesh_skin else []
finite = all(math.isfinite(v) for v in bbox1)
for j in cmds.ls("ROPE_BIND_*_JNT",type="joint") or []:
    finite = finite and all(math.isfinite(v) for v in cmds.xform(j,q=True,ws=True,m=True))

report = {
    "scene": SCENE,
    "tests": tests,
    "followPresetWeights": follow_values,
    "manualFollowWeights": manual_values,
    "meshSkin": mesh_skin,
    "meshSkinInfluences": len(infs),
    "nodeCounts": {
        "bindJoints": len(cmds.ls("ROPE_BIND_*_JNT",type="joint") or []),
        "curveDrivers": len(cmds.ls("CURVE_DRIVER_*_JNT",type="joint") or []),
        "mainIK": len(cmds.ls("MAIN_IK_*_CTRL",type="transform") or []),
        "secondaryIK": len(cmds.ls("SECONDARY_IK_*_CTRL",type="transform") or []),
        "sculpt": len(cmds.ls("SCULPT_*_CTRL",type="transform") or []),
        "fk": len(cmds.ls("FK_*_CTRL",type="transform") or []),
    },
    "returnedBBoxDelta": max(abs(bbox1[i]-bbox0[i]) for i in range(6)),
    "finite": finite,
}
expected = [[[.5,.5,0],[1,0,0],[0,1,0],[0,0,1]][i] for i in range(4)]
presets_ok = len(follow_values)==4 and all(max(abs(follow_values[i][k]-expected[i][k]) for k in range(3)) < 1e-5 for i in range(4))
manual_ok = len(manual_values)==3 and max(abs(manual_values[i]-[.2,.7,.1][i]) for i in range(3)) < 1e-5
report["passed"] = (
    all(tests[k] > 0.02 for k in ("mainIK","secondaryIK","sculpt","fk","knotPivot","lassoOpen","lassoDrop"))
    and tests["stretchRatio"] > 1.03 and tests["twistMatrixDelta"] > .01
    and presets_ok and manual_ok and len(infs)==41 and report["returnedBBoxDelta"] < .001 and finite
)
print("FIXED_VALIDATION_JSON=" + json.dumps(report, ensure_ascii=False))
maya.standalone.uninitialize()
