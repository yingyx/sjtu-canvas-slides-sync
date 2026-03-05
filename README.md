![](assets/banner.svg)

<p align="center">
  <img align="center" src="https://img.shields.io/github/license/yingyx/sjtu-canvas-slides-sync" /> 
  <img align="center" src="https://img.shields.io/github/forks/yingyx/sjtu-canvas-slides-sync" /> 
  <img align="center" src="https://img.shields.io/github/stars/yingyx/sjtu-canvas-slides-sync" />
</p>

本项目支持将 [SJTU Canvas](https://oc.sjtu.edu.cn/) 的文件定期同步至 [交大云盘](https://pan.sjtu.edu.cn/)，结合 [TboxWebdav](https://github.com/1357310795/TboxWebdav/) 项目可实现“本地”打开 Canvas 文件，而不额外占用本地空间的优雅体验。此外，还支持自动将 `.pptx` 等格式的文件转换成 PDF 格式，方便在笔记软件中打开。

## 使用
- 点击右上角 `Fork`，点击 `Create Fork`
- 点击上方 `Settings`，滑动到最下方，点击 `Leave fork network` 并确认
- 刷新页面，在相邻的位置点击 `Change visibility` 并确认
- 点击设置页面左侧的 `Secrets and variables` 下方的 `Actions`，按照下表，分别点击 `New repository secret` 进行设置

| Name | Secret |
| - | - |
| CANVAS_TOKEN | 打开 [Canvas 设置页面](https://oc.sjtu.edu.cn/profile/settings)，点击 `创建新访问许可证`，随意填写用途，点击 `生成令牌`，复制令牌并填入 |
| SMH_USER_TOKEN | 打开 [交大云盘](https://pan.sjtu.edu.cn/)，按下 `F12` 或 `Ctrl+Shift+I` 打开开发者工具，在 `应用——Cookie` 中找到 `USER_TOKEN`，左键双击对应的 `值` 一栏，复制并填入 |

- 点击上方 `Actions`，点选 `Canvas Auto Sync`，并点击 `Enable workflow`（具体说明见 [https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows)）

## 配置项

- 定时执行规则：通过 [`sync.yml`](.github/workflows/sync.yml) 中的 `on——schedule——cron` 可配置定时执行规则，请参考 [GitHub 文档](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onschedule) 或 [crontab.guru](https://crontab.guru/)
- 是否将 PPT 转换为 PDF：将 [`sync.yml`](.github/workflows/sync.yml) 中的 `Run Sync` 步骤下的 `CONVERT_PPT_TO_PDF` 设置为 `true`/`false`

## 注意事项
- 连续 60 天无文件更新后，workflow 将被 GitHub 自动停用，可参考 [操作步骤](#操作步骤) 章节最后一步重新启用 workflow
- workflow 的输出中可能会包含 `CANVAS_TOKEN`、`SMH_USER_TOKEN` 等敏感信息，因此建议通过 [操作步骤](#操作步骤) 第 2、3 步将仓库设为 private

## 参考资料
- https://cloud.tencent.com/product/smh