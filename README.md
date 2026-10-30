# Dialogue Blips · 逐字对话音效

给 Unity 游戏《深空当铺 / Probably Stolen》做的**程序化逐字对话音效** Mod：NPC 每显示一个字符，
就播一段按角色定制的短合成音（RPG 式「嘚嘚嘚」）。

**不采样任何音频文件**——所有声音由 bfxr 合成器实时参数化生成。

## 它做什么

- **22 套音色**：4 个通用音色覆盖约 110 个原型 NPC，18 个具名角色各有专属音色
- **人物识别**四层链：本地化显示名 → spriteName → identifier → 性别×语域兜底
- **游戏内面板（F11）**：三级参数分类、18 项可调参数、实时数值、层的增删、音色包切换与导出
- **音色包机制**：`.json` 包可切换 / 导入 / 导出 / 按依赖自动接管
- **Agent 文件接口**：外部 AI 通过两个 JSON 文件读写音色，不开端口、不申请网络权限

## 目录

```
mod/DialogueBlips/      Unity Mod 源码（C#，netstandard2.1）
  src/                  Mod.cs / PersonaResolver.cs / VoiceBank.cs / Panel.cs / Agent.cs
  lib/bfxr/             内置 bfxr 合成器（第三方，见下）
  characters.json       人物键表
bfxr-host/              本地调音台（.NET 10 + 网页，开发用，不进游戏）
packs/                  出厂音色包
tools（根目录 *.py）   打包、生成、测量、回归脚本
checks/                 回归测试
需求汇总_*.md           需求与决策记录
移交手册_完整版_*.md    完整交接文档（先读这个）
```

## 构建

需要游戏本体的程序集作引用（`Private=false`，不会打包进发布物）。

```powershell
cd mod/DialogueBlips
dotnet build
# 产物：bin/Debug/netstandard2.1/DialogueBlips.dll
```

部署到 `.../Probably Stolen/Mods/player.dialogueblips/`。
⚠️ 游戏运行时 DLL 被内存映射锁定，**必须先退出游戏**再复制。

调音台：

```powershell
cd bfxr-host
dotnet run -- serve 8731      # http://127.0.0.1:8731/
```

## 许可

本项目采用 **GNU AGPL-3.0**，全文见 [LICENSE](LICENSE)。

选 AGPL 而不是 MIT，是希望任何改进过这个 Mod 的分发版本都把改动放回社区——
包括通过网络提供服务的形态。

### 第三方

内置的 bfxr 合成器来自 `tedwikman/com.wikman.synthesizer`，保留其原有许可：

| 部分 | 许可 |
|---|---|
| 包装层 | MIT |
| BFXR（`SfxrGenerator.cs` 等） | **MPL-2.0** |
| `SfxrParams` / `SfxrSynth` | Apache-2.0 |

- MPL-2.0 是**文件级 copyleft**：`lib/bfxr/` 下被修改过的源文件必须保持公开。
  本项目对该目录有一处修改（`[MOD FIX]` 注释标出：原包把音量/包络那一行注释掉了，导致削波刺耳）。
- MPL-2.0 与 Apache-2.0 均可与本项目的 AGPL-3.0 组合分发。
- 完整许可见 `mod/DialogueBlips/licenses/`。

### 不包含的内容

游戏文本、剧情提取物与游戏美术资源**不在本仓库内**——它们属于游戏版权方。
`characters.json` 只包含让 Mod 工作需要的最少量角色名与本地化键。


## 音色设计方法

音色是怎么设计出来的、公式与踩过的坑，都写在 [skill/blip-voice-design/SKILL.md](skill/blip-voice-design/SKILL.md)。
改音色之前先读它，能省掉一轮返工。
