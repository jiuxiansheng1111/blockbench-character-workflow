# Minecraft 角色建模工作流

**这是基于 Minecraft 方块与像素风格的角色建模插件，供 Codex 配合 Blockbench 使用。** 它按参考拆解脸型、五官、长方体发束和身体比例，实际修改可编辑模型，保护用户已经认可的部件，并用真实渲染逐轮对照。

建模目标是制作适合 Minecraft 场景的角色资源：以长方体结构、清晰像素色块、可辨认的轮廓和游戏距离下的可读性为基础。接入游戏时必须适配具体 Minecraft 版本、Java/Bedrock 格式与模组加载器；通用 Blockbench 工程不会自动获得跨版本兼容性。

这是从多轮角色建模修改中整理的工作方法与工具。它不会凭一句提示词保证角色相似度，也不把 `.bbmodel` 自动等同于游戏模型。**不是安装进 Blockbench 的 JavaScript 扩展**；可配合 Blockbench 桌面端、可用的建模工具或可选 MCP 使用。

## 包含内容

- `blockbench-character-modeling` 技能：先参考分析和本轮简报，再脸型/五官、方块发束、比例修改、真实预览与交付。
- 四份实操参考：提示词写法、几何规则、工具与导出、审阅清单。
- `bbmodel_audit.py`：只读检查结构、UV、纹理索引、旋转特征；冻结指定组并比较几何、祖先变换和共用贴图依赖。
- `contact_sheet.py`：排列真实模型截图并记录原图 SHA-256，不修脸、不重画、不冒充渲染器。
- 标准插件清单与本仓库 marketplace，便于作为插件安装。

## 安装

在支持插件 marketplace 的 Codex CLI 中：

```sh
codex plugin marketplace add jiuxiansheng1111/blockbench-character-workflow
codex plugin add blockbench-character-modeling@jiuxiansheng-modeling
```

私有仓库需要已有 GitHub 读取权限。也可以克隆仓库，在支持本地 marketplace 的客户端中打开这个仓库，通过插件目录选择本仓库的“Minecraft 角色建模”。按客户端提示刷新或重启使新插件生效；本项目不会自行重启应用。

插件布局依据 [OpenAI 插件打包文档](https://developers.openai.com/plugins/build/plugins)：`plugins/blockbench-character-modeling/plugin.json` 为入口，兼容清单位于 `.codex-plugin/plugin.json`，仓库的 `.agents/plugins/marketplace.json` 指向插件目录。

## 使用

在会话中提供实际模型和参考，并说明本轮目标。例如：

> 使用 $blockbench-character-modeling。保留这版身体和裙子，按参考修脸型、眼睛和刘海；长发长度不变。改完亲自对比正侧背面，先交付本地 Blockbench 工程。

说明已认可的基线版本很重要。插件会区分建模、导入编辑器、接入游戏、安装与实机验收；使用中仍遵循用户当前授权和项目约定。

## 本地工具

需要 Python 3.10+。审计和冻结工具无第三方依赖；拼图使用 Pillow（需自行在所用环境安装）。从下面目录运行：

```sh
cd plugins/blockbench-character-modeling/skills/blockbench-character-modeling
python scripts/bbmodel_audit.py audit character.bbmodel --cuboids-only --output audit.json
python scripts/bbmodel_audit.py snapshot baseline.bbmodel --group body --group skirt --output locked.json
python scripts/bbmodel_audit.py compare candidate.bbmodel --baseline locked.json --output comparison.json
python scripts/contact_sheet.py --image front=front.png --image side=side.png --image back=back.png --output views.png
```

组名重复时传组 UUID。`snapshot` 要求引用贴图已嵌入，避免只锁住外部文件名却漏掉贴图改动。共用 atlas 的任何像素改变都会保守地报变化，需要人工复查。工具拒绝覆盖已有输出。审计退出码：0 结构检查通过，1 发现结构错误或锁定变化，2 输入/运行错误。

审计不计算世界空间穿插、法线正确性或相似度。拼图不生成模型渲染；要先由真实编辑器/渲染器导出图片。中文标签可用 `--font` 指定本地中文字体。

## 可选建模连接

[Blockbench MCP 上游项目](https://github.com/jasonjgardner/blockbench-mcp-plugin) 提供桌面 HTTP 与 headless stdio 能力。此插件不包含上游实现，不替你安装、连接、开放端口或启用 `risky_eval`。按上游当前说明配置，并先完成一个简单模型的创建、读取、真实渲染，再开始复杂角色。工具路径、账号、代理端口没有写死在本插件中。

## 验证与限制

查看 [VALIDATION.md](VALIDATION.md) 了解本版本实际执行的检查。仓库上传不等于插件已在所有客户端安装验证；静态检查不等于角色美术或 Minecraft 实机验收。

仓库只包含原创工作流和辅助代码，不包含用户角色模型、参考图片、第三方贴图/网格/动画、游戏整合包、聊天记录或凭证。参考作品和外部工具各自保留原有权利，参见 [NOTICE.md](NOTICE.md)。
