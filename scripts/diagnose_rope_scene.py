import json
import math
import os
import sys

import maya.standalone
maya.standalone.initialize(name="python")
import maya.cmds as cmds

SCENE = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\haoguoli\Desktop\shengzi\shengzi_Rig_FINAL.ma"
cmds.file(SCENE, o=True, f=True, prompt=False)

geo = "ROPE_GEO"
shape = (cmds.listRelatives(geo, s=True, ni=True, f=True) or [None])[0]
bbox = cmds.exactWorldBoundingBox(geo)
lengths = [bbox[i+3]-bbox[i] for i in range(3)]
axis = lengths.index(max(lengths))
cross = [i for i in range(3) if i != axis]
verts_flat = cmds.xform(geo + ".vtx[*]", q=True, ws=True, t=True)
verts = [verts_flat[i:i+3] for i in range(0, len(verts_flat), 3)]

def dist(a,b):
    return math.sqrt(sum((a[i]-b[i])**2 for i in range(3)))

joints = sorted(cmds.ls("ROPE_BIND_*_JNT", type="joint") or [])
joint_positions = [cmds.xform(j, q=True, ws=True, t=True) for j in joints]
nearest = []
for p in joint_positions:
    nearest.append(min(dist(p,v) for v in verts))

# Estimate the actual mesh centerline by binning vertices along its longest world axis.
bins = []
for i in range(len(joints)):
    u = i / float(max(1, len(joints)-1))
    target = bbox[axis] + lengths[axis] * u
    half_width = lengths[axis] / max(4.0, (len(joints)-1)*2.0)
    sample = [v for v in verts if abs(v[axis]-target) <= half_width]
    if not sample:
        sample = sorted(verts, key=lambda v: abs(v[axis]-target))[:50]
    c = [sum(v[k] for v in sample)/len(sample) for k in range(3)]
    c[axis] = target
    bins.append(c)
centerline_error = [dist(joint_positions[i], bins[i]) for i in range(len(joints))]

curve = "ROPE_DRIVER_CRV"
curve_cvs = [cmds.pointPosition(cv, w=True) for cv in cmds.ls(curve+".cv[*]", fl=True)] if cmds.objExists(curve) else []
skin = (cmds.ls(type="skinCluster") or [None])[0]
influences = cmds.skinCluster(skin, q=True, inf=True) if skin else []

data = {
    "scene": SCENE,
    "geo": geo,
    "geoParent": cmds.listRelatives(geo,p=True,f=True),
    "geoTranslate": cmds.xform(geo,q=True,ws=True,t=True),
    "geoRotate": cmds.xform(geo,q=True,ws=True,ro=True),
    "bbox": bbox,
    "lengths": lengths,
    "majorAxis": "XYZ"[axis],
    "vertexCount": len(verts),
    "jointCount": len(joints),
    "jointRootParent": cmds.listRelatives(joints[0],p=True,f=True) if joints else [],
    "jointPositions": {"first":joint_positions[0] if joints else None,"middle":joint_positions[len(joints)//2] if joints else None,"last":joint_positions[-1] if joints else None},
    "meshCenters": {"first":bins[0] if bins else None,"middle":bins[len(bins)//2] if bins else None,"last":bins[-1] if bins else None},
    "nearestVertexDistance": {"min":min(nearest) if nearest else None,"mean":sum(nearest)/len(nearest) if nearest else None,"max":max(nearest) if nearest else None},
    "centerlineError": {"min":min(centerline_error) if centerline_error else None,"mean":sum(centerline_error)/len(centerline_error) if centerline_error else None,"max":max(centerline_error) if centerline_error else None},
    "curveCVs": {"count":len(curve_cvs),"first":curve_cvs[0] if curve_cvs else None,"middle":curve_cvs[len(curve_cvs)//2] if curve_cvs else None,"last":curve_cvs[-1] if curve_cvs else None},
    "skinCluster": skin,
    "skinInfluenceCount": len(influences),
    "skinGeometry": cmds.skinCluster(skin,q=True,g=True) if skin else [],
    "selection": cmds.ls(sl=True),
}
print("DIAGNOSTIC_JSON=" + json.dumps(data, ensure_ascii=False))
maya.standalone.uninitialize()
