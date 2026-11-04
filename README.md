# Maya Rope Rig

Maya 2025 绳索绑定工程，包含修正版场景、自动构建脚本和验证工具。

## 文件结构

- `scenes/shengzi_Rig_FIXED.ma`：完成并验证的 Maya ASCII 绑定场景。
- `scripts/build_rope_rig_v2.py`：从源模型自动重建绑定的脚本。
- `scripts/validate_rope_rig_fixed.py`：主/次 IK、Sculpt、FK、绳结、套索、拉伸、扭转及跟随权重验证。
- `scripts/diagnose_rope_scene.py`：模型中心线与骨骼位置诊断工具。
- `reports/rope_rig_fixed_report.json`：构建后的自动验证报告。

## 绑定系统

- 41 根中心线绑定骨骼与 Spline IK。
- 9 个主 IK、8 个次级 IK、17 个 Sculpt 控制器和 9 个 FK 控制器。
- 次级 IK 支持 Both、Left、Right、World 四种跟随模式以及自定义权重混合。
- 独立绳结与套索局部塑形控制层。
- 弧长拉伸、截面体积补偿和高级扭转控制。

## 验证结果

- 骨骼中心线平均误差：`0.000679` Maya 单位。
- 骨骼中心线最大误差：`0.005950` Maya 单位。
- 绑定前后模型包围盒偏差：`0`。
- 主 IK、次级 IK、Sculpt、FK、绳结、套索、拉伸、扭转及跟随权重测试均通过。

## 环境

- Autodesk Maya 2025
- Python 3（Maya 内置 Python）

