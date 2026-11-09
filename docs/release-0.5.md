# 0.5 更新说明

0.5 是拿 0.4 真干了一周活（两个项目、三百多张卡）之后的一版，修的都是真碰上的坑：可以有好几个首领，
首领一接上就看得清每只猫，卡住会报、撤卡会停，失败写清断在哪，猫干完会接着处理你中途的留言，
记录和临时文件不再越攒越大。界面布局这一版没动大样子（0.6 再改）。

## 可以有好几个首领

- 工位页「再加一个首领」：两个项目各开一个对话当首领时，给其中一个对话一个新首领的地址。
  每个首领只看自己派的卡、只收自己卡的交回、只能验自己的卡；猫是大家共用的，闲着的猫谁都能派。
- 两个对话连着同一个首领时，盒子会在首领的回话里、工位页和办公室里明说，提醒你再加一个首领。
  只是重开了一次对话不算。
- 看板上写清每只猫在给哪个首领干。

## 首领看得更清楚

- 首领一接上（`get_briefing` / `get_board`）就看到每只猫的模型、接活方式、现在能不能接、余量、歇着的几点回来。
  Cursor 里派活时，工位是下拉可选的。
- 首领每次回话末尾都带「还等你处理：N 张」和卡号标题，漏看一次也不会把卡忘在那儿。
- 看板、卡详情和首领回话里的状态字跟实际一致：跑完、失败、等验收的卡不再写「排队中」。
- 等交回（`wait_for_update`）最多 100 秒：不会再在 Cursor 里超时报错。
- 打回时说明字段写错名字（比如写成 comment）会被拒并说清楚该叫什么；空说明的打回不收。
- 卡失败写清断在哪：跑了多久、几轮、最后一次动静、最后跑的命令和报错几行、产出目录里现在有几个文件。
  做到一半断的不再写成「没跑成」。

## 卡住会报，撤卡会停

- 命令很久没新输出、模型很久没回话、很久不调用工具，待办里标「可能卡住」，写清是哪条命令。
  单条命令跑太久会被停下，卡记失败、对话留着，可以再派接着做。时长都在设置页「高级」里改。
- 撤掉一张在跑的卡，会把它起的整棵进程一起停掉，猫马上回到能派活。
- 打工猫跑 git 不会再卡在编辑器或密码提示上。

## 派活更顺

- 打回重派时猫还在忙，这张就排在它后面，不会同时跑两张；到了上限再派，带的是这次的新说明。
- 给在跑的猫留言（`post`）：猫干完这一轮会接着同一段对话处理你的留言，不用打回重跑。
- 派卡撞车提醒按卡上的 `files` 比，不再只因为工作目录一样就报。
- 模型 id 或密钥配错的猫，标成「配置有问题」，不再接活，提醒你去工位页改；改好就恢复。
  首领可以用 `resolve` 把卡改派给别的猫，卡号不变。
- 断网时卡排队、网通了接着原来的对话做；这期间猫写清「几点再探」。

## 余量和花了多少

- 同一把 key 的几只猫显示同一个余量（以前各查各的，3 只猫能显示 3 个数）。
- 看板加了「效率」：近 7 天每只猫、每张卡的用时、轮数、用量、缓存命中，模型和命令各占多少时间，
  测试跑了几遍、最长的一条命令；有公开单价的估一个钱。

## 打工猫说明书 v5

- 只跑和改动相关的测试，整套留给 CI 或合并之后；可能超过 2 分钟的命令带超时；先搜到行再读那一段，不整文件读。
- 猫的临时目录是这张卡专用的，卡结束会清，要留的东西写到卡上的产出目录。
- 首领写卡指南：一轮把能并行的卡都派出去；并行的卡不要都改版本号 / CHANGELOG；代码卡自己开 worktree，不用目录联接。
- 老用户的说明书第一次用到时自动换成新的，旧的留一份 `.bak`。

## 不再越攒越大

- 运行记录只记有用的：逐字流出来的片段、长命令每次重发的全部输出、重复打包的事件都不记。
  一次运行的记录从几十到几百 MB 降到一两 MB。
- 结束的卡（完成 / 撤掉 / 失败）的运行记录过 3 天压成 .gz，过 30 天删掉；卡片和回报留着。
  天数、要不要完整记录，都在设置页「高级」里改。
- 设置页「数据和隐私」能看到 `data\` 占多少、其中运行记录多少，一键压缩结束的卡的记录。
- 卡完成或撤掉就清掉它的临时目录；失败、中断的先留着查。删的时候碰到目录联接只删联接本身，不会顺着删进你的项目。

## 升级

- 最简单：从托盘退出 0.4，把新 exe 放进原来那个文件夹，双击。`data\` 沿用。
- 要放新文件夹：先退出旧版，再到新版设置页「数据和隐私」→「从旧版导入」，填旧版文件夹。
  不要在旧版还开着时拷 `data\`：拷完之后旧版里新派的卡、交回和验收都不会带过来。

## 其它修复

- 设置页几行按钮被挤成一字一行、英文窄窗口横向溢出。
- 看板卡详情里一个标题露出了没翻译的键名。
- AI 软件断开连接时，`tray.log` 里不再刷整段报错。
- 后台启动命令行（没有控制台）时不再崩。

## 已知问题

- 同一个 AI 软件窗口里的两个对话可能共用一条连接，盒子认不出是两个对话。各开一个首领就没有这个问题。
- 从 0.4 升上来的老运行没有「模型 / 命令各占多少」，效率面板里显示「—」。
- 工位名还不能改（0.6 做）。
- AI 客户端跑在 WSL 里时连不到盒子：盒子只听 Windows 本机的 127.0.0.1。
- 目前只有 Windows 版（Windows 10 / 11，64 位）。
- exe 是 PyInstaller 打的单文件包，每次启动会先解压到临时目录再运行，个别杀毒软件会因此误报。

---

## In English (short)

0.5 fixes what a week of real use of 0.4 turned up. Highlights: several leaders (each sees and reviews only its own
cards; the box warns when two chats share one leader); the leader sees each cat's model, quota and when it is back
the moment it connects, and every reply lists the cards still waiting on it; stuck runs are flagged and cancelling
a card stops its whole process tree; failures say where and why a run stopped; notes to a working cat are picked up
when it finishes; cats with a wrong model id or key are taken off the list until fixed; one quota per key; a new
Efficiency panel; worker manual v5; run records are slimmed, compressed after 3 days and deleted after 30 (all
adjustable); temp folders are cleared when a card finishes. To upgrade, quit 0.4 and put the new exe in the same
folder, or use Settings → Data and privacy → Import from an old version.
