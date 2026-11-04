from __future__ import annotations

import json
import math
import os
import traceback

import maya.standalone
maya.standalone.initialize(name="python")
import maya.cmds as cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma


SOURCE = r"C:\Users\haoguoli\Desktop\shengzi\shengzi_Rig.ma"
OUTPUT = r"C:\Users\haoguoli\Desktop\shengzi\shengzi_Rig_FIXED_v2.ma"
REPORT = r"C:\Users\haoguoli\CodeBuddy\Claw\butterfly_knife\rope_rig_fixed_v2_report.json"


def color(ctrl, index):
    for shape in cmds.listRelatives(ctrl, s=True, ni=True, f=True) or []:
        cmds.setAttr(shape + ".overrideEnabled", 1)
        cmds.setAttr(shape + ".overrideColor", index)


def add_attr(node, name, at="double", **kwargs):
    if not cmds.attributeQuery(name, node=node, exists=True):
        cmds.addAttr(node, ln=name, at=at, **kwargs)
    return node + "." + name


def add_string(node, name, value):
    if not cmds.attributeQuery(name, node=node, exists=True):
        cmds.addAttr(node, ln=name, dt="string")
    cmds.setAttr(node + "." + name, value, type="string")


def circle_ctrl(name, pos, radius, normal, col, parent):
    zero = cmds.group(em=True, n=name + "_ZERO")
    space = cmds.group(em=True, n=name + "_SPACE", p=zero)
    ctrl = cmds.circle(n=name, ch=False, nr=normal, r=radius, s=16)[0]
    cmds.parent(ctrl, space)
    cmds.xform(zero, ws=True, t=pos)
    cmds.parent(zero, parent)
    color(ctrl, col)
    return ctrl, zero, space


def box_ctrl(name, pos, radius, col, parent):
    r = radius
    pts = [(-r,-r,-r),(r,-r,-r),(r,r,-r),(-r,r,-r),(-r,-r,-r),(-r,-r,r),
           (r,-r,r),(r,r,r),(-r,r,r),(-r,-r,r),(r,-r,r),(r,-r,-r),
           (r,r,-r),(r,r,r),(-r,r,r),(-r,r,-r)]
    zero = cmds.group(em=True, n=name + "_ZERO")
    space = cmds.group(em=True, n=name + "_SPACE", p=zero)
    ctrl = cmds.curve(n=name, d=1, p=pts)
    cmds.parent(ctrl, space)
    cmds.xform(zero, ws=True, t=pos)
    cmds.parent(zero, parent)
    color(ctrl, col)
    return ctrl, zero, space


def diamond_ctrl(name, pos, radius, col, parent):
    r = radius
    pts = [(r,0,0),(0,r,0),(-r,0,0),(0,-r,0),(r,0,0),(0,0,r),
           (-r,0,0),(0,0,-r),(r,0,0),(0,r,0),(0,0,r),(0,-r,0),(0,0,-r),(0,r,0)]
    zero = cmds.group(em=True, n=name + "_ZERO")
    space = cmds.group(em=True, n=name + "_SPACE", p=zero)
    ctrl = cmds.curve(n=name, d=1, p=pts)
    cmds.parent(ctrl, space)
    cmds.xform(zero, ws=True, t=pos)
    cmds.parent(zero, parent)
    color(ctrl, col)
    return ctrl, zero, space


def connect(src, dst):
    if cmds.isConnected(src, dst):
        return
    cmds.connectAttr(src, dst, f=True)


def find_geo():
    candidates = []
    for shape in cmds.ls(type="mesh", l=True) or []:
        if cmds.getAttr(shape + ".intermediateObject"):
            continue
        p = cmds.listRelatives(shape, p=True, f=True) or []
        if p:
            candidates.append(p[0])
    if not candidates:
        raise RuntimeError("No mesh found")
    candidates.sort(key=lambda x: cmds.polyEvaluate(x, v=True), reverse=True)
    return candidates[0]


def mesh_data(geo, sample_count=17):
    bbox = cmds.exactWorldBoundingBox(geo)
    lengths = [bbox[i+3]-bbox[i] for i in range(3)]
    axis = lengths.index(max(lengths))
    flat = cmds.xform(geo + ".vtx[*]", q=True, ws=True, t=True)
    verts = [flat[i:i+3] for i in range(0, len(flat), 3)]
    points = []
    for i in range(sample_count):
        u = i / float(sample_count - 1)
        target = bbox[axis] + lengths[axis] * u
        half = lengths[axis] / float((sample_count - 1) * 2.2)
        sample = [v for v in verts if abs(v[axis] - target) <= half]
        if not sample:
            sample = sorted(verts, key=lambda v: abs(v[axis] - target))[:64]
        p = [sum(v[k] for v in sample) / len(sample) for k in range(3)]
        p[axis] = target
        points.append(p)
    radial = []
    for v in verts[::max(1, len(verts)//1000)]:
        u = (v[axis]-bbox[axis]) / max(lengths[axis], 1e-8)
        idx = min(sample_count-1, max(0, int(round(u*(sample_count-1)))))
        radial.append(math.sqrt(sum((v[k]-points[idx][k])**2 for k in range(3) if k != axis)))
    radius = sorted(radial)[int(len(radial)*0.90)] if radial else max(lengths)*0.01
    return bbox, lengths, axis, verts, points, max(radius, lengths[axis]*0.002)


def interp(points, u):
    x = max(0.0, min(1.0, u)) * (len(points)-1)
    a = int(math.floor(x))
    b = min(len(points)-1, a+1)
    t = x-a
    return [points[a][k]*(1-t)+points[b][k]*t for k in range(3)]


def set_skin_weights(skin, geo, joints, verts, bbox, axis):
    sel = om.MSelectionList()
    sel.add(skin)
    skin_obj = sel.getDependNode(0)
    fn = oma.MFnSkinCluster(skin_obj)
    sel2 = om.MSelectionList()
    shape = cmds.listRelatives(geo, s=True, ni=True, f=True)[0]
    sel2.add(shape)
    dag = sel2.getDagPath(0)
    comp_fn = om.MFnSingleIndexedComponent()
    comp = comp_fn.create(om.MFn.kMeshVertComponent)
    comp_fn.addElements(list(range(len(verts))))
    inf_paths = fn.influenceObjects()
    names = [p.partialPathName() for p in inf_paths]
    index_map = {name: i for i, name in enumerate(names)}
    inf_ids = om.MIntArray(range(len(inf_paths)))
    weights = om.MDoubleArray(len(verts) * len(inf_paths), 0.0)
    span = bbox[axis+3]-bbox[axis]
    for vi, v in enumerate(verts):
        u = max(0.0, min(1.0, (v[axis]-bbox[axis]) / max(span, 1e-8)))
        f = u*(len(joints)-1)
        a = int(math.floor(f))
        b = min(len(joints)-1, a+1)
        t = f-a
        weights[vi*len(inf_paths)+index_map[joints[a]]] = 1.0-t
        weights[vi*len(inf_paths)+index_map[joints[b]]] += t
    fn.setWeights(dag, comp, inf_ids, weights, True)


def add_follow_system(ctrl, zero, left, right, world_loc, index):
    add_attr(ctrl, "followMode", "enum", en="Both:Left:Right:World", k=True)
    add_attr(ctrl, "useCustomFollow", "bool", dv=0, k=True)
    for name, dv in [("followLeft",.5),("followRight",.5),("followWorld",0.0)]:
        add_attr(ctrl, name, "double", dv=dv, min=0.0, max=1.0, k=True)
    add_string(ctrl, "followHelp", "Preset modes are no-pop in Maya UI; enable Custom Follow and key weights for smooth transitions.")
    pc = cmds.parentConstraint(left, right, world_loc, zero, mo=True, n=zero + "_FOLLOW_PC")[0]
    aliases = cmds.parentConstraint(pc, q=True, wal=True)
    presets = [(0.5,1.0,0.0,0.0),(0.5,0.0,1.0,0.0),(0.0,0.0,0.0,1.0)]
    attrs = ["followLeft","followRight","followWorld"]
    for wi, (both,leftv,rightv,worldv) in enumerate(presets):
        choice = cmds.createNode("choice", n="SECONDARY_IK_%02d_FOLLOW_%d_CHOICE" % (index,wi))
        connect(ctrl + ".followMode", choice + ".selector")
        for slot,val in enumerate((both,leftv,rightv,worldv)):
            cmds.setAttr(choice + ".input[%d]" % slot, val)
        blend = cmds.createNode("blendTwoAttr", n="SECONDARY_IK_%02d_FOLLOW_%d_BLEND" % (index,wi))
        connect(choice + ".output", blend + ".input[0]")
        connect(ctrl + "." + attrs[wi], blend + ".input[1]")
        connect(ctrl + ".useCustomFollow", blend + ".attributesBlender")
        connect(blend + ".output", pc + "." + aliases[wi])
    return pc


def build():
    cmds.file(SOURCE, o=True, f=True, prompt=False)
    geo = find_geo()
    if geo.split("|")[-1] != "ROPE_GEO":
        geo = cmds.rename(geo, "ROPE_GEO")
    bbox, lengths, axis, verts, centerline, radius = mesh_data(geo, 17)
    major = lengths[axis]
    normal = [0,0,0]
    normal[axis] = 1
    ctrl_r = radius * 2.8
    center = centerline[len(centerline)//2]

    root = cmds.group(em=True, n="ROPE_RIG_ROOT")
    global_ctrl, global_zero, _ = box_ctrl("GLOBAL_CTRL", center, ctrl_r*2.0, 17, root)
    rope_ctrl, rope_zero, _ = circle_ctrl("ROPE_CTRL", center, ctrl_r*1.55, normal, 22, global_ctrl)
    controls_grp = cmds.group(em=True, n="CONTROLS_GRP", p=rope_ctrl)
    deform_grp = cmds.group(em=True, n="DEFORM_SYSTEM_GRP", p=rope_ctrl)
    # Geometry stays in world space. The skin receives GLOBAL/ROPE motion from the
    # bind joints only, preventing the classic double-transform problem.
    geo_grp = cmds.group(em=True, n="GEOMETRY_GRP", p=root)
    cmds.setAttr(geo_grp + ".inheritsTransform", 0)
    modules_grp = cmds.group(em=True, n="MODULES_GRP", p=rope_ctrl)
    world_grp = cmds.group(em=True, n="WORLD_SPACES_GRP", p=root)
    cmds.setAttr(world_grp + ".inheritsTransform", 0)
    cmds.parent(geo, geo_grp)

    vis_attrs = [("showGeometry",1),("showMainIK",1),("showSecondaryIK",1),("showSculpt",1),
                 ("showFK",1),("showJoints",0),("showKnot",1),("showLasso",1)]
    for name,dv in vis_attrs:
        add_attr(global_ctrl,name,"bool",dv=dv,k=True)
    add_attr(global_ctrl,"globalScale","double",dv=1.0,min=0.001,k=True)
    for a in "XYZ": connect(global_ctrl+".globalScale",global_ctrl+".scale"+a)

    fk_grp = cmds.group(em=True,n="FK_CONTROLS_GRP",p=controls_grp)
    main_grp = cmds.group(em=True,n="MAIN_IK_CONTROLS_GRP",p=controls_grp)
    sec_grp = cmds.group(em=True,n="SECONDARY_IK_CONTROLS_GRP",p=controls_grp)

    fk_controls=[]
    parent=fk_grp
    for i in range(9):
        pos=centerline[i*2]
        c,z,_=circle_ctrl("FK_%02d_CTRL"%(i+1),pos,ctrl_r*1.20,normal,14,parent)
        fk_controls.append(c); parent=c

    main_controls={}
    main_zeros={}
    for mi,ci in enumerate(range(0,17,2)):
        c,z,_=circle_ctrl("MAIN_IK_%02d_CTRL"%(mi+1),centerline[ci],ctrl_r,normal,13,main_grp)
        cmds.parentConstraint(fk_controls[mi],z,mo=True,n=z+"_FK_PC")
        add_attr(c,"tangentScale","double",dv=1.0,min=0.05,max=5.0,k=True)
        add_attr(c,"localStretch","double",dv=1.0,min=0.05,max=5.0,k=True)
        main_controls[ci]=c; main_zeros[ci]=z

    sec_controls={}
    for si,ci in enumerate(range(1,16,2)):
        c,z,_=circle_ctrl("SECONDARY_IK_%02d_CTRL"%(si+1),centerline[ci],ctrl_r*.72,normal,6,sec_grp)
        loc=cmds.spaceLocator(n="SECONDARY_IK_%02d_WORLD_LOC"%(si+1))[0]
        cmds.xform(loc,ws=True,t=centerline[ci]); cmds.parent(loc,world_grp); cmds.setAttr(loc+".visibility",0)
        add_follow_system(c,z,main_controls[ci-1],main_controls[ci+1],loc,si+1)
        add_attr(c,"tangentScale","double",dv=1.0,min=0.05,max=5.0,k=True)
        add_attr(c,"localStretch","double",dv=1.0,min=0.05,max=5.0,k=True)
        sec_controls[ci]=c

    driver_curve=cmds.curve(n="ROPE_DRIVER_CRV",d=3,p=centerline)
    cmds.parent(driver_curve,deform_grp)
    cmds.setAttr(driver_curve+".visibility",0)
    driver_joints=[]; sculpt_controls=[]; sculpt_zeros=[]
    for i,pos in enumerate(centerline):
        base=main_controls[i] if i in main_controls else sec_controls[i]
        sc,sz,_=diamond_ctrl("SCULPT_%02d_CTRL"%(i+1),pos,ctrl_r*.34,17,base)
        sculpt_controls.append(sc); sculpt_zeros.append(sz)
        cmds.select(clear=True)
        j=cmds.joint(n="CURVE_DRIVER_%02d_JNT"%(i+1),p=pos,rad=radius*.18)
        cmds.parent(j,sc)
        cmds.setAttr(j+".drawStyle",2)
        driver_joints.append(j)

    curve_skin=cmds.skinCluster(driver_joints,driver_curve,tsb=True,bm=0,sm=0,nw=1,mi=3,omi=True,n="ROPE_CURVE_SKIN")[0]
    for i in range(17):
        weights=[]
        if i>0: weights.append((driver_joints[i-1],.15))
        weights.append((driver_joints[i],.70 if 0<i<16 else .85))
        if i<16: weights.append((driver_joints[i+1],.15))
        total=sum(v for _,v in weights)
        weights=[(j,v/total) for j,v in weights]
        cmds.skinPercent(curve_skin,driver_curve+".cv[%d]"%i,tv=weights,normalize=True)

    # Main and secondary scale attributes change curve tangent reach and local length.
    for ci,ctrl in list(main_controls.items())+list(sec_controls.items()):
        md=cmds.createNode("multiplyDivide",n=ctrl.replace("_CTRL","_TANGENT_SCALE_MD"))
        connect(ctrl+".tangentScale",md+".input1X"); connect(ctrl+".localStretch",md+".input2X")
        for a in "XYZ":
            if "XYZ".index(a)==axis: connect(md+".outputX",ctrl+".scale"+a)
            else: connect(ctrl+".tangentScale",ctrl+".scale"+a)

    # Spline bind chain lies on the evaluated curve before binding the mesh.
    cmds.select(clear=True)
    bind_joints=[]
    for i in range(41):
        p=interp(centerline,i/40.0)
        bind_joints.append(cmds.joint(n="ROPE_BIND_%03d_JNT"%(i+1),p=p,rad=radius*.28))
    cmds.joint(bind_joints[0],e=True,oj="xyz",sao="yup",ch=True,zso=True)
    cmds.parent(bind_joints[0],deform_grp)
    ikh,eff=cmds.ikHandle(n="ROPE_SPLINE_IKH",sj=bind_joints[0],ee=bind_joints[-1],sol="ikSplineSolver",
                          c=driver_curve,ccv=False,pcv=False,roc=True)
    cmds.parent(ikh,deform_grp); cmds.setAttr(ikh+".visibility",0)
    cmds.setAttr(ikh+".dTwistControlEnable",1); cmds.setAttr(ikh+".dWorldUpType",4)
    cmds.setAttr(ikh+".dWorldUpVector",0,1,0,type="double3")
    cmds.setAttr(ikh+".dWorldUpVectorEnd",0,1,0,type="double3")
    connect(main_controls[0]+".worldMatrix[0]",ikh+".dWorldUpMatrix")
    connect(main_controls[16]+".worldMatrix[0]",ikh+".dWorldUpMatrixEnd")
    cmds.refresh(force=True)

    ci=cmds.createNode("curveInfo",n="ROPE_ARCLENGTH_CIF")
    connect(cmds.listRelatives(driver_curve,s=True,ni=True)[0]+".worldSpace[0]",ci+".inputCurve")
    rest=cmds.getAttr(ci+".arcLength")
    ratio=cmds.createNode("multiplyDivide",n="ROPE_STRETCH_RATIO_MD"); cmds.setAttr(ratio+".operation",2)
    connect(ci+".arcLength",ratio+".input1X"); cmds.setAttr(ratio+".input2X",rest)
    volume=cmds.createNode("multiplyDivide",n="ROPE_VOLUME_MD"); cmds.setAttr(volume+".operation",3)
    connect(ratio+".outputX",volume+".input1X"); cmds.setAttr(volume+".input2X",-.5)
    for j in bind_joints[:-1]:
        connect(ratio+".outputX",j+".scaleX"); connect(volume+".outputX",j+".scaleY"); connect(volume+".outputX",j+".scaleZ")

    pre_bbox=cmds.exactWorldBoundingBox(geo)
    mesh_skin=cmds.skinCluster(bind_joints,geo,tsb=True,bm=0,sm=0,nw=1,mi=2,omi=True,n="ROPE_SKINCLUSTER")[0]
    set_skin_weights(mesh_skin,geo,bind_joints,verts,bbox,axis)
    cmds.refresh(force=True)

    # Knot deformation module (three independent pivots).
    knot_grp=cmds.group(em=True,n="KNOT_MODULE_GRP",p=modules_grp)
    knot_root,knot_zero,_=box_ctrl("KNOT_GLOBAL_CTRL",centerline[3],ctrl_r*.82,21,knot_grp)
    cmds.parentConstraint(main_controls[4],knot_zero,mo=True)
    add_attr(knot_root,"stretch","double",dv=1.0,min=.1,max=5.0,k=True)
    add_attr(knot_root,"modelVisibility","bool",dv=1,k=True); add_attr(knot_root,"controlVisibility","bool",dv=1,k=True)
    knot_controls=[]
    for ki,idx in enumerate((2,3,4)):
        kc,kz,_=circle_ctrl("KNOT_PIVOT_%02d_CTRL"%(ki+1),centerline[idx],ctrl_r*(.58-ki*.06),normal,21,knot_root)
        knot_controls.append(kc)
        root_offset=cmds.group(em=True,n="KNOT_ROOT_%02d_OFFSET"%(ki+1),p=sculpt_controls[idx])
        cmds.xform(root_offset,ws=True,t=centerline[idx])
        offset=cmds.group(em=True,n="KNOT_PIVOT_%02d_OFFSET"%(ki+1),p=root_offset)
        cmds.xform(offset,ws=True,t=centerline[idx]); cmds.parent(driver_joints[idx],offset)
        for a in ("translate","rotate","scale"): connect(knot_root+"."+a,root_offset+"."+a)
        for a in ("translate","rotate","scale"): connect(kc+"."+a,offset+"."+a)

    # Lasso deformation module (size/open/drop controls).
    lasso_grp=cmds.group(em=True,n="LASSO_MODULE_GRP",p=modules_grp)
    lasso_root,lasso_zero,_=box_ctrl("LASSO_GLOBAL_CTRL",centerline[14],ctrl_r*.86,9,lasso_grp)
    cmds.parentConstraint(main_controls[14],lasso_zero,mo=True)
    for name,dv,mn,mx in [("loopSize",1.0,.1,5.0),("loopOpen",0.0,-major*.3,major*.3),("sag",0.0,-major*.3,major*.3),("stretch",1.0,.1,5.0)]:
        add_attr(lasso_root,name,"double",dv=dv,min=mn,max=mx,k=True)
    add_attr(lasso_root,"modelVisibility","bool",dv=1,k=True); add_attr(lasso_root,"controlVisibility","bool",dv=1,k=True)
    lasso_controls=[]
    for label,idx in (("SIZE",12),("OPEN",14),("DROP",16)):
        lc,lz,_=diamond_ctrl("LASSO_%s_CTRL"%label,centerline[idx],ctrl_r*.48,9,lasso_root)
        lasso_controls.append(lc)
        root_offset=cmds.group(em=True,n="LASSO_ROOT_%s_OFFSET"%label,p=sculpt_controls[idx])
        cmds.xform(root_offset,ws=True,t=centerline[idx])
        offset=cmds.group(em=True,n="LASSO_%s_OFFSET"%label,p=root_offset)
        cmds.xform(offset,ws=True,t=centerline[idx]); cmds.parent(driver_joints[idx],offset)
        for a in ("translate","rotate","scale"): connect(lasso_root+"."+a,root_offset+"."+a)
        for a in ("translate","rotate","scale"): connect(lc+"."+a,offset+"."+a)
    for a in "XYZ": connect(lasso_root+".loopSize",lasso_controls[0]+".scale"+a)
    cross=[i for i in range(3) if i!=axis]
    connect(lasso_root+".loopOpen",lasso_controls[1]+".t"+"xyz"[cross[0]])
    connect(lasso_root+".sag",lasso_controls[2]+".t"+"xyz"[cross[1]])

    # The module offset hierarchy is now final. Rebind the driver curve so parent
    # motion from the Knot/Lasso Global controls is not cancelled by bind matrices.
    cmds.delete(curve_skin)
    curve_skin=cmds.skinCluster(driver_joints,driver_curve,tsb=True,bm=0,sm=0,nw=1,mi=3,omi=True,n="ROPE_CURVE_SKIN")[0]
    for i in range(17):
        weights=[]
        if i>0: weights.append((driver_joints[i-1],.15))
        weights.append((driver_joints[i],.70 if 0<i<16 else .85))
        if i<16: weights.append((driver_joints[i+1],.15))
        total=sum(v for _,v in weights)
        cmds.skinPercent(curve_skin,driver_curve+".cv[%d]"%i,
                         tv=[(j,v/total) for j,v in weights],normalize=True)
    cmds.refresh(force=True)

    # Visibility controls.
    connect(global_ctrl+".showGeometry",geo_grp+".visibility")
    connect(global_ctrl+".showMainIK",main_grp+".visibility")
    connect(global_ctrl+".showSecondaryIK",sec_grp+".visibility")
    connect(global_ctrl+".showFK",fk_grp+".visibility")
    connect(global_ctrl+".showJoints",bind_joints[0]+".visibility")
    connect(global_ctrl+".showKnot",knot_grp+".visibility"); connect(global_ctrl+".showLasso",lasso_grp+".visibility")
    for z in sculpt_zeros: connect(global_ctrl+".showSculpt",z+".visibility")

    all_ctrls=[global_ctrl,rope_ctrl]+fk_controls+list(main_controls.values())+list(sec_controls.values())+sculpt_controls+[knot_root]+knot_controls+[lasso_root]+lasso_controls
    cmds.sets(all_ctrls,n="ROPE_ALL_CONTROLS_SET")
    cmds.sets(bind_joints,n="ROPE_BIND_JOINTS_SET")
    info=cmds.createNode("network",n="ROPE_RIG_INFO")
    add_string(info,"version","2.1-feedback-fix")
    add_string(info,"sourceScene",SOURCE); add_string(info,"referenceVideo",r"C:\Users\haoguoli\Desktop\Video Project 1.mp4")
    add_string(info,"controlLegend","Red Main IK; Blue Secondary IK; Yellow Sculpt; Green FK; Orange Knot; Pink Lasso")
    add_string(info,"deformation","Curve skin drivers (no clusters), 41-joint spline IK, explicit two-joint mesh weights, stretch and volume preservation")
    add_attr(info,"restArcLength","double",dv=rest)

    # UI no-pop follow switch script. It preserves the blue control's world matrix when enum mode changes.
    setup = "import maya.cmds as cmds\n"
    setup += "g=globals()\n"
    setup += "for j in g.get('_ropeFollowJobs',[]):\n    try: cmds.scriptJob(kill=j,force=True)\n    except: pass\n"
    setup += "g['_ropeFollowState']={}\ng['_ropeFollowJobs']=[]\n"
    setup += "cs=cmds.ls('SECONDARY_IK_*_CTRL',type='transform') or []\n"
    setup += "for c in cs: g['_ropeFollowState'][c]=cmds.xform(c,q=True,ws=True,m=True)\n"
    setup += "def _ropeCache():\n    for c in cmds.ls('SECONDARY_IK_*_CTRL',type='transform') or []:\n        if cmds.objExists(c): g['_ropeFollowState'][c]=cmds.xform(c,q=True,ws=True,m=True)\n"
    setup += "def _ropeMatch(c):\n    m=g['_ropeFollowState'].get(c)\n    if m:\n        cmds.refresh(f=True); cmds.xform(c,ws=True,m=m)\n    g['_ropeFollowState'][c]=cmds.xform(c,q=True,ws=True,m=True)\n"
    setup += "for c in cs: g['_ropeFollowJobs'].append(cmds.scriptJob(attributeChange=[c+'.followMode',lambda x=c:_ropeMatch(x)],protected=True))\n"
    setup += "g['_ropeFollowJobs'].append(cmds.scriptJob(idleEvent=_ropeCache,protected=True))\n"
    cmds.scriptNode(n="ROPE_FOLLOW_NOPOP_SETUP",st=2,bs=setup,stp="python")

    # Validation: alignment, deformation response, return to bind pose and finite matrices.
    post_bbox=cmds.exactWorldBoundingBox(geo)
    joint_pos=[cmds.xform(j,q=True,ws=True,t=True) for j in bind_joints]
    center_samples=[interp(centerline,i/40.0) for i in range(41)]
    align=[math.sqrt(sum((joint_pos[i][k]-center_samples[i][k])**2 for k in range(3))) for i in range(41)]
    def cvp(i): return cmds.pointPosition(driver_curve+".cv[%d]"%i,w=True)
    def d(a,b): return math.sqrt(sum((a[k]-b[k])**2 for k in range(3)))
    cross_attr="t"+"xyz"[[i for i in range(3) if i!=axis][0]]
    before=cvp(8); cmds.setAttr(main_controls[8]+"."+cross_attr,major*.06); cmds.refresh(f=True); main_delta=d(before,cvp(8)); cmds.setAttr(main_controls[8]+"."+cross_attr,0); cmds.refresh(f=True)
    before=cvp(7); cmds.setAttr(sec_controls[7]+"."+cross_attr,-major*.04); cmds.refresh(f=True); sec_delta=d(before,cvp(7)); cmds.setAttr(sec_controls[7]+"."+cross_attr,0); cmds.refresh(f=True)
    before=cvp(8); cmds.setAttr(sculpt_controls[8]+"."+cross_attr,major*.02); cmds.refresh(f=True); sculpt_delta=d(before,cvp(8)); cmds.setAttr(sculpt_controls[8]+"."+cross_attr,0); cmds.refresh(f=True)
    end_ctrl=main_controls[16]; tattr="t"+"xyz"[axis]; base_arc=cmds.getAttr(ci+".arcLength"); cmds.setAttr(end_ctrl+"."+tattr,major*.10); cmds.refresh(f=True); stretch_ratio=cmds.getAttr(ci+".arcLength")/base_arc; cmds.setAttr(end_ctrl+"."+tattr,0); cmds.refresh(f=True)

    def bbox_center():
        b=cmds.exactWorldBoundingBox(geo)
        return [(b[i]+b[i+3])*.5 for i in range(3)]
    global_test_value=5.0
    c0=bbox_center(); cmds.setAttr(global_ctrl+".tx",global_test_value); cmds.refresh(f=True); c1=bbox_center()
    global_move=c1[0]-c0[0]; cmds.setAttr(global_ctrl+".tx",0); cmds.refresh(f=True)
    c0=bbox_center(); cmds.setAttr(rope_ctrl+".tx",global_test_value); cmds.refresh(f=True); c1=bbox_center()
    rope_move=c1[0]-c0[0]; cmds.setAttr(rope_ctrl+".tx",0); cmds.refresh(f=True)

    before=cvp(3); cmds.setAttr(knot_root+"."+cross_attr,major*.025); cmds.refresh(f=True); knot_global_delta=d(before,cvp(3)); cmds.setAttr(knot_root+"."+cross_attr,0); cmds.refresh(f=True)
    before=cvp(14); cmds.setAttr(lasso_root+"."+cross_attr,major*.025); cmds.refresh(f=True); lasso_global_delta=d(before,cvp(14)); cmds.setAttr(lasso_root+"."+cross_attr,0); cmds.refresh(f=True)
    final_bbox=cmds.exactWorldBoundingBox(geo)
    report={"output":OUTPUT,"axis":"XYZ"[axis],"meshLength":major,"radius":radius,
            "jointCenterlineError":{"mean":sum(align)/len(align),"max":max(align)},
            "bindPoseBBoxDelta":max(abs(post_bbox[i]-pre_bbox[i]) for i in range(6)),
            "returnedBBoxDelta":max(abs(final_bbox[i]-post_bbox[i]) for i in range(6)),
            "tests":{"mainIK":main_delta,"secondaryIK":sec_delta,"sculpt":sculpt_delta,"stretchRatio":stretch_ratio,
                     "globalTranslateInput":global_test_value,"globalMeshTranslate":global_move,
                     "ropeTranslateInput":global_test_value,"ropeMeshTranslate":rope_move,
                     "knotGlobal":knot_global_delta,"lassoGlobal":lasso_global_delta},
            "counts":{"bindJoints":len(bind_joints),"mainIK":len(main_controls),"secondaryIK":len(sec_controls),"sculpt":len(sculpt_controls),"fk":len(fk_controls)}}
    report["passed"]=(max(align)<radius*.35 and report["bindPoseBBoxDelta"]<radius*.05
                      and main_delta>radius*.1 and sec_delta>radius*.1 and sculpt_delta>radius*.05
                      and stretch_ratio>1.001 and abs(global_move-global_test_value)<.001
                      and abs(rope_move-global_test_value)<.001
                      and knot_global_delta>radius*.1 and lasso_global_delta>radius*.1
                      and report["returnedBBoxDelta"]<radius*.05)

    cmds.select(global_ctrl,r=True)
    cmds.file(rename=OUTPUT); cmds.file(save=True,type="mayaAscii",force=True)
    with open(REPORT,"w",encoding="utf-8") as f: json.dump(report,f,ensure_ascii=False,indent=2)
    print("ROPE_FIXED_REPORT="+json.dumps(report,ensure_ascii=False))
    return report


try:
    RESULT=build()
finally:
    maya.standalone.uninitialize()
