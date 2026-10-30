# 给上传 Agent · 1.0.0 工坊包修订

一句话：**别用之前那个 zip，改用 `DialogueBlips-1.0.0-workshop.zip`。** 内容一模一样，只改了打包结构。

## 上传这个文件

```
D:\AI\blip-lab\dist\release-1.0.0\DialogueBlips-1.0.0-workshop.zip
SHA-256  FADFD0F318EEF7133A4F7BBDE9F54882E3A41782678F19CB553EF63CBFB8E79C
```

## 为什么换

工坊要求 `manifest.xml` 在**项目根目录**。之前上传的是「手工安装版」，里面多套了一层 `player.dialogueblips/`，于是玩家的工坊目录变成：

```
<工坊ID>\player.dialogueblips\manifest.xml   ← 游戏在这一层找不到清单
```

游戏只在根目录找清单，所以报「无法安装 / 要更新清单文件」。两个玩家报的是同一句话，就是这个原因。

正确的样子（对照工坊里其他 20 多个能用的 Mod，全部如此）：

```
<工坊ID>\
  manifest.xml
  DialogueBlips.dll
  packs\
  ...
```

## 怎么确认拿对了

解压后**第一层**应该直接看到：

```
manifest.xml
DialogueBlips.dll
characters.json
packs\  licenses\  source\
LICENSE  LICENSE.md  Third Party Notices.md
安装说明.txt  源码与许可.txt
```

看到 `player.dialogueblips\` 这一层，就是拿错了。

## 已经验证过

- 构建脚本会断言工坊包根层一定有 `manifest.xml` 和 `DialogueBlips.dll`，没有就构建失败
- 解压后的 24 个文件与手工安装版逐一对应，只是去掉了外层目录

## 你之前改的东西保留

- `manifest.xml` 里 `<Author>` 改成「啊啊啊~哈稽道人」——**保留**，我已经提交进包了
- 封面图在 `封面发布_2026-10-30\`——**没有进 git**，那是你的产出，你自己决定怎么用
- `skill/blip-voice-design/SKILL.md.bak`——也没有进 git，你收尾时删掉就行

## 需要重做测试吗

**不用。** 语音、参数、音色包内容一个字节都没变，改的只是外层目录。之前测过的都还有效。

## 如果旧版已经有人订阅了

已经订阅到错误结构的玩家，可能需要**取消订阅再重新订阅**。或者你在工坊项目里更新内容后，Steam 会重新下发一次——具体看玩家那边有没有清缓存。

---

顺带：手工安装分发（网盘、群文件）仍然用另一个文件 `DialogueBlips-1.0.0.zip`，那个**要**套一层 `player.dialogueblips\` 文件夹，别搞反了。
