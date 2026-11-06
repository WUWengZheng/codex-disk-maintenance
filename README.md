# Codex Disk Maintenance · Codex 磁盘维护

**简体中文** | [English](README.en.md)

为 Codex 提供磁盘诊断、迭代成果管理、聊天内清理提醒和任务收尾能力：**保留最终成果、必要依赖及记忆，多轮交付后提醒清理，用户回复“需要”再回收中间文件，把任务经验持续维护在一个 Markdown 文件中。**

适用于 macOS，核心脚本使用 Python 3.9+ 标准库，无第三方 Python 运行依赖。

> 技能在当前聊天被加载并持续使用后，可以在多轮成果交付时主动提醒清理。安装本身不创建后台服务、定时任务或聊天结束钩子，也不能保证每个聊天都会触发；新任务可用下面的一句话明确启用。

## 最简单的使用方式

在任务开始或继续优化时说一次：

> **使用 $codex-disk-maintenance，在本次任务多轮交付后提醒清理，我回复“需要”再执行。**

之后正常修改成果。出现具体清理提醒时，只需回复 **“需要”**；Codex 会更新同一个经验文件，复核后清理本次提醒中的旧版。回复“暂不需要”则保留文件，同一批结果不反复提醒。

已有成果需要立即整理时：

> 使用 $codex-disk-maintenance 整理项目成果，清理中间版本，更新经验记录。

需要明确保留范围时：

> 整理本次对话的成果，保留最终版和必要源文件，删除明确不再需要的中间结果；把有效经验汇总到唯一的《经验记录.md》，后续修改持续更新这个文件。

日常也可以分别调用：

| 你的需求 | 示例指令 |
| --- | --- |
| 检查空间 | 使用 $codex-disk-maintenance 检查 Codex 磁盘占用，先不要清理。 |
| 多轮后提醒 | 使用 $codex-disk-maintenance，在本次任务多轮交付后提醒清理，我回复“需要”再执行。 |
| 管理后续迭代 | 使用 $codex-disk-maintenance，这次只保留最终结果，清理中间版本。 |
| 标记定稿 | 这版定稿，保留整套最终成果和必要素材。 |
| 识别历史版本 | 使用 $codex-disk-maintenance 检查指定文件夹的迭代版本，先列出候选。 |
| 任务收尾 | 整理项目成果，清理中间版本，更新经验记录。 |

新聊天中，显式写出 `$codex-disk-maintenance` 更容易准确选中技能。单说“整理一下项目”含义较宽，可能被理解为代码或目录整理。

## 它解决什么问题

Codex 执行任务时，工作目录、依赖、渲染图片、转换文件、测试输出和多轮优化结果可能持续积累。目录名叫 `tmp` 或 `cache`，并不能证明里面所有内容都可以删除。

这个技能提供两类能力：

- **确定性脚本**：计量目录、比较基线、校验清单、记录替代关系、保护经验文件、检查使用状态、执行受限回收。
- **Codex 工作指导**：根据当前任务上下文确认交付成果及依赖，撰写经验，选择已授权的动作，解释不确定项。

文件内容的语义判断与经验总结由 Codex 根据可用任务证据完成。Python 脚本不会自动理解任意文档、恢复聊天上下文，或证明任意文件的依赖已经完整。

## 功能与边界

| 功能 | 已实现行为 |
| --- | --- |
| 占用扫描 | 读取元数据，输出逻辑大小、分配块大小、最大目录与文件、覆盖情况 |
| 增长比较 | 保存签名基线，比较两次完整且可比较的扫描范围 |
| 临时工作区 | 创建专用目录、记录结束状态和保留声明；结束满 24 小时后才有资格回收 |
| 缓存维护 | 使用 pip、uv、npm、pnpm 原生命令；每种工具有独立检查条件 |
| 历史版本识别 | 按同目录、同格式的名称及版本号提出候选，不凭修改时间删除 |
| 迭代版本登记 | 记录任务、成果、版本、明确替代关系和多格式交付包 |
| 聊天内清理提醒 | 同一成果在当前聊天成功交付至少 3 轮且有可安全回收的前驱时提出具体建议；回复“需要”后执行，同一建议不重复询问 |
| 旧版回收 | 仅处理被有效定稿明确替代、且已授权的登记文件 |
| 单一经验 MD | 每个任务绑定一个经验文件路径，后续原位更新并保护它 |
| 操作记录 | 清理前落盘，保留完成、跳过、失败和部分完成信息 |

**当前不提供**：全天候监控、自动跨聊天触发、任意历史文件一键清空、worktree 直接删除、聊天或记忆数据库压缩、系统快照删除、全局语义查重。

## 安装

### 方式一：让 Codex 安装

将仓库链接交给 Codex，要求把该仓库安装为用户技能：

```text
请将 https://github.com/WUWengZheng/codex-disk-maintenance 安装为 Codex skill。
```

### 方式二：Git 克隆到技能目录

```sh
skill_install_root="${CODEX_HOME:-$HOME/.codex}/skills"
mkdir -p "$skill_install_root"
git clone https://github.com/WUWengZheng/codex-disk-maintenance.git \
  "$skill_install_root/codex-disk-maintenance"
```

若目标目录已存在，先核对内容，不要直接覆盖。重新进入聊天后确认技能可用；也可通过绝对路径明确指定 `SKILL.md`。

仅运行脚本时，克隆到普通工作目录即可，不要求安装到 Codex。

### 更新

在已安装目录没有本地修改时，可以执行：

```sh
git -C "${CODEX_HOME:-$HOME/.codex}/skills/codex-disk-maintenance" pull --ff-only
```

已有手工安装副本时，先比较并保留本地修改，再采用 Git 安装方式。更新后，在后续聊天中重新加载技能；进行中的聊天可明确要求读取更新后的 `SKILL.md`。

## 成果多轮优化如何处理

```text
任务：论文图 6
v1.svg → v2.svg → v3.svg + v3.png（最终交付）
                         └── 必要依赖：plot.py、assets/
```

最终交付包及依赖全部保留。只有明确被定稿替代的前驱版本才进入回收候选。

- `v4` 如果是试验稿或失败导出，不会自动取代已交付的 `v3`。
- 不同格式可能是同一交付包，不默认互相替代。
- 未被替代的独立方案、其他任务的成果继续保留。
- 定稿或依赖丢失、发生变化时，停止回收相关旧版。
- 已有文件缺乏可靠替代关系时，先由 Codex 核对当前任务证据，必要时询问最终版；不会只保留修改时间最新的文件。

## 多轮交付后的清理提醒

技能在当前聊天中管理迭代时，每次成功交付登记一个版本及其替代关系；同一轮导出的 SVG、PNG、PDF 是一个交付包，不按文件数量计算轮次。草稿、工具重试和失败导出不计入成功交付轮次。

默认在同一成果于**当前聊天成功交付至少 3 轮**、并且存在通过检查的明确前驱文件时，在交付末尾提出清理建议。例如：

```text
Codex：第 3 版已交付。发现 2 个被最终版替代的中间文件（约 80 MiB）。
       保留最终成果、必要源文件和经验记录，需要清理吗？回复“需要”即可。
你：需要。
Codex：更新原有经验记录，重新核对待清理文件与定稿，执行通过检查的回收并报告结果。
```

这类提醒只提出建议，不提前删除文件。数量和大小来自实际候选清单，大小是估计，不能保证释放同等磁盘空间。

- 每个聊天只保留一份当前待确认建议，可以包含同一任务的多个成果；建议绑定实际文件、定稿状态和当前聊天。
- 对同一定稿和候选不重复询问。拒绝或过期后也不持续催促；有新的成功交付和新候选时才可能再次提醒。
- “需要”“可以清理”等明确答复，只有在直接回应当前具体清理建议时才构成授权。其他话题中的“需要”、引用或假设不触发清理。
- 授权只覆盖这份建议中的中间结果，不包含其他任务、缓存、worktree、聊天或记忆。执行前先更新并保护任务唯一的经验 MD；尚未绑定时，由 Codex 创建并绑定 `经验记录.md`。
- 建议有效期为 **24 小时**。执行前仍需复核原候选和定稿；过期、文件改变或仍在使用时停止相关回收，不擅自扩大范围或改用更强的清理方式。
- 确认只使用一次。中断或部分失败后呈现实际结果，不自动重复删除。没有可靠替代关系或安全候选时，不为凑够轮次而提出删除建议。

这属于技能被加载后的聊天内工作流，没有跨聊天监听器。其他聊天的历史版本不计入本次聊天的交付轮次。正常的技能自动选择仍可使用；要确保本次任务启用，可显式说出 `$codex-disk-maintenance` 和上面的提醒指令。

## 唯一的经验记录文件

任务收尾按下面的顺序执行：

1. 确认最终交付包和依赖。
2. 读取并更新已有任务经验文件；首次使用默认在该任务输出目录创建 `经验记录.md`。
3. 绑定并保护经验文件。
4. 清理已授权且通过检查的旧版本。
5. 在聊天中简短报告实际处理结果和文件位置。

经验文件保存有依据的结论、有效方法、失败原因、必要命令和简短变更记录。重复经验合并，过时结论标明替代关系。若用户明确只要一条经验，则维护一条主要经验。

后续修改写回同一个文件，不生成 `经验记录_v2.md` 或每天一个总结文件。不同任务各自使用自己的目录和绑定，不混合无关项目。经验 MD 不等于聊天历史，也不会自动导入 MemPalace 或全局记忆。

脚本只负责绑定和保护文件；总结正文由 Codex 编写。机器操作日志仍会保留，不属于额外的人类可读经验总结。

## 命令行参考

以下命令从仓库根目录执行。示例中的 `/absolute/...`、任务名和版本号需要替换为实际值。

### 1. 扫描与基线

```sh
# 默认范围：Codex 数据、相关应用目录、临时目录、工具缓存
python3 scripts/disk_maintenance.py scan

# 严格限定范围，关闭默认根目录和工具发现
python3 scripts/disk_maintenance.py scan --root /absolute/task

# 在默认范围中增加项目，并显式保存基线
python3 scripts/disk_maintenance.py scan --project /absolute/project --save-baseline

# 聚焦登记过的临时工作区和原生缓存，保持扫描预算
python3 scripts/disk_maintenance.py scan --candidates-only --save-baseline

# 比较最近两次基线，或给出两个明确路径
python3 scripts/disk_maintenance.py diff
python3 scripts/disk_maintenance.py diff /absolute/before.json /absolute/after.json
```

默认预算是 120 秒、50 万个文件系统条目。达到预算时返回部分结果，未完整覆盖的对象不能作为删除证据。首次检查不能证明“今天增长了多少”。

扫描普通文件元数据，不读取普通文件正文；不跟随符号链接，跳过嵌套挂载点及特殊文件。原生工具查询可能产生其自身的少量日志。

### 2. 清理清单与执行

```sh
# 使用 scan 返回的 saved_path
python3 scripts/disk_maintenance.py plan --scan /absolute/saved-scan.json

# 只执行授权的类别；还可以用 --ids 限定项目
python3 scripts/disk_maintenance.py apply \
  --plan /absolute/saved-plan.json --authorize scratch pnpm
```

扫描基线用于制定清单的有效期为 15 分钟；清单也在 15 分钟后过期。执行前会重新核对目标和使用状态。需要重新扫描时，仍遵循原来的授权范围。

pip/npm 的整体缓存清空必须明确加入清单：

```sh
python3 scripts/disk_maintenance.py plan \
  --scan /absolute/saved-scan.json --include-full-cache-clear
python3 scripts/disk_maintenance.py apply \
  --plan /absolute/saved-plan.json --authorize pip npm
```

这会增加后续下载或构建成本，不能承诺清单中的缓存总大小都能释放。

### 3. 专用临时工作区

```sh
python3 scripts/disk_maintenance.py scratch create
# 使用返回的工作区存放可丢弃中间文件
python3 scripts/disk_maintenance.py scratch finish --run-id RUN_ID
# 如果仍有成果留在里面，声明保留；整个工作区都会被保护
python3 scripts/disk_maintenance.py scratch finish \
  --run-id RUN_ID --keep relative/result.pdf
```

无法把任意历史目录直接登记为可丢弃目录。未结束、结束不足 24 小时、存在保留声明或正在使用的工作区不能回收。

### 4. 识别和登记迭代版本

```sh
python3 scripts/iterations.py inspect --root /absolute/task

python3 scripts/iterations.py track \
  --task paper --artifact figure6 --revision v1 --chat CHAT_ID --final \
  --file /absolute/figure6_v1.svg

python3 scripts/iterations.py track \
  --task paper --artifact figure6 --revision v2 --replaces v1 --chat CHAT_ID \
  --file /absolute/figure6_v2.svg --file /absolute/figure6_v2.png \
  --dependency /absolute/plot.py --dependency /absolute/assets --final

python3 scripts/iterations.py review
```

`--file`、`--dependency`、`--replaces` 可以重复。登记后的版本不可修改；文件变动后应登记新版本。`--final` 表示明确交付，不能仅因为文件名含 `final` 就设置。提醒只统计带有当前聊天 ID 的成功交付版本；`--chat` 未提供时使用环境中的 `CODEX_THREAD_ID`（如果存在），其他聊天或未绑定聊天的历史版本不计数。

### 5. 绑定经验文件与回收旧版

先由 Codex 创建或更新该文件，再绑定：

```sh
python3 scripts/iterations.py notes \
  --task paper --file /absolute/task/经验记录.md
```

一个任务绑定一个路径，重复绑定相同路径可用，改绑另一文件会被拒绝。经验文件可正常原位修改；不要把它登记为不可变版本或依赖快照。绑定文件缺失时，清理会停止。

下面是**实际删除**命令，只在已核对最终成果、依赖和授权范围后执行：

```sh
python3 scripts/iterations.py prune \
  --task paper --artifact figure6 --authorize-superseded
```

它只删除明确的前驱版本文件，不清空任务目录，不自动保留一个“最新文件”而删除其余全部内容。迭代旧版回收不使用临时工作区的 24 小时规则；依据是明确替代关系和有效定稿。

### 6. 生成提醒、确认或暂缓

当前聊天使用稳定且独有的 `CHAT_ID`，与其他聊天区分；`TASK` 仍表示当前任务。每次成功交付后，由 Codex 检查是否需要提醒。下面沿用前两轮示例，登记第三次交付：

```sh
python3 scripts/iterations.py track \
  --task paper --artifact figure6 --revision v3 --replaces v2 --chat CHAT_ID \
  --file /absolute/figure6_v3.svg --file /absolute/figure6_v3.png \
  --dependency /absolute/plot.py --dependency /absolute/assets --final

python3 scripts/iterations.py remind --task paper --chat CHAT_ID
```

返回 `status: offered` 时，展示其中的候选范围、保留范围、数量及大小估计。使用返回的 `offer_id`；不要手写或复用其他聊天的建议 ID。再次检查同一建议不会重复提醒。

用户直接确认这份建议后，先更新并绑定唯一的经验文件，再执行：

```sh
# 实际删除：仅在用户已明确同意当前具体建议后运行
python3 scripts/iterations.py confirm \
  --chat CHAT_ID --offer-id OFFER_ID --authorize-superseded
```

若用户说“暂不需要”，记录暂缓，不删除文件：

```sh
python3 scripts/iterations.py dismiss --chat CHAT_ID --offer-id OFFER_ID
```

提醒有效期、文件复核及一次性确认独立于临时工作区的冷却期。普通 `prune` 仍可用于用户直接授权的整理，不需要先凑够三轮；提醒也不会自行授予缓存清理权限。

## 缓存适配器

| 工具 | 原生命令 | 限制 |
| --- | --- | --- |
| uv | `uv cache prune` | 默认因历史符号链接依赖未核实而跳过 |
| pnpm | `pnpm store prune` | 检查 store 使用状态和相关进程 |
| pip | `pip cache purge` | 单独授权整体缓存清空 |
| npm | `npm cache clean --force` | 单独授权整体缓存清空 |

仅支持代码中列明的常规缓存位置；自定义位置目前只诊断。工具缺失不会触发安装。npm/pnpm 检测到 Node 进程时会保守跳过。

uv 只有在操作者已确认不存在保留环境通过符号链接依赖缓存时，才可以为该次调用提供 `DISK_MAINTENANCE_UV_NO_SYMLINK_DEPENDENCIES=1`。技能不会自动设置这个断言来绕过检查。

详细路径、版本下限及参数见 [清理规则](references/cleanup-rules.md)。

## 数据保护、状态与恢复

默认状态目录：

```text
${CODEX_HOME:-~/.codex}/disk-maintenance/
├── signing.key             本地签名密钥
├── registry.json           临时工作区登记
├── outputs-registry.json   成果版本、经验文件绑定与清理提醒
├── scan-*.json             占用基线
├── plan-*.json             清理清单
└── result-*.json           操作记录
```

- 主脚本支持全局 `--codex-home` 和 `--state-dir`，放在子命令前；版本脚本支持 `--state-dir`。
- `CODEX_HOME` 默认 `~/.codex`。状态目录须由用户拥有，权限为 `0700`。
- HMAC 用于检测清单及登记记录被改动，不是对同一用户账户中恶意程序的隔离机制。
- 最多保留 30 次占用基线，状态总量限制为 20 MiB。签名密钥、临时登记和成果登记不自动轮换；必要元数据超预算时停止写入。
- worktree、聊天、记忆数据库、凭据、技能、运行时、最终成果及必要依赖默认保护。未知历史文件不因年龄或名称自动删除。
- 删除前检查完整性、文件身份、使用状态及审计写入。清理器使用单实例锁。
- 临时工作区先在同一文件系统内改名复核。旧成果也使用同目录临时改名和身份检查；不会复制一份大型备份，也不会靠移动到废纸篓宣称释放空间。
- 中断可能导致部分完成。按操作记录检查原路径和隔离路径，保留剩余文件，不自动重试删除或覆盖后来新建的同名文件。
- 不执行系统快照删除、进程终止或数据库维护。命令超时只处理本次创建的子命令。

脚本输出带类型标记的 JSON。退出码 `2` 表示顶层拒绝或错误；退出码 `0` 的结果仍可能包含跳过、失败或部分完成项，必须阅读每项状态。

文件逻辑大小、分配块大小和文件系统可用空间是不同指标。APFS 克隆、硬链接、快照及并发写入会影响结果，删除大小不能直接等同于实际释放空间。

## 测试与验证

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

测试只使用隔离目录和模拟包管理器，覆盖占用与增长、符号链接与硬链接、扫描预算、清单篡改、文件变化、使用状态、磁盘写满、命令失败、最终成果保护、版本替代关系、唯一经验 MD 绑定，以及提醒去重、聊天隔离、过期和确认时复核等场景。

Skill 格式可用 Codex 自带的 `skill-creator/scripts/quick_validate.py` 检查。这个开发用验证器需要 PyYAML；核心脚本和单元测试仍只用标准库。

## 目录结构

```text
codex-disk-maintenance/
├── README.md                 中文说明
├── README.en.md              English documentation
├── SKILL.md
├── agents/openai.yaml
├── scripts/
│   ├── disk_maintenance.py
│   └── iterations.py
├── references/
│   ├── cleanup-rules.md
│   └── iteration-results.md
└── tests/
    ├── test_disk_maintenance.py
    ├── test_iterations.py
    └── test_reminders.py
```

## 常见问题

**安装后会每天自动删除吗？**

不会。定时任务、会话钩子及后台监控尚未实现或配置。

**为什么没有自动提醒？**

先确认当前聊天已加载新版本技能，并使用它管理本次迭代。同一成果需要当前聊天中至少三轮成功交付和安全候选；仅聊天轮次很多、文件多或文件较旧都不足以触发。同一建议不会重复催促，技能也不会监听其他聊天。

**只回复“需要”，会不会把所有缓存和旧文件都删掉？**

不会。它只授权刚刚展示的当前聊天清理建议。定稿、必要依赖和唯一经验文件继续保留；候选改变、建议过期或检查失败时不会照旧删除。

**能把任意旧成果自动判断成“无用”吗？**

不能。历史名称识别只提供提示；可靠回收需要当前任务证据、明确替代关系和有效定稿。

**只保留一个 MD，是不是其他成果也删掉？**

不是。一个 MD 指经验文档数量；最终文档、图片、可编辑文件和必要素材继续保留。

**经验文件会自动写进 MemPalace 吗？**

不会。经验只维护在当前任务绑定的 MD 中，不自动导入全局记忆。

**能保证释放某个固定容量吗？**

不能。会报告实际观察到的变化和未能回收的原因。

**怎样反馈问题？**

在 [Issues](https://github.com/WUWengZheng/codex-disk-maintenance/issues) 描述命令、系统/Python 版本、脱敏后的结果和预期行为。不要上传原始聊天、扫描报告、密钥或私有成果。

## 贡献

修改脚本时请同时验证行为与数据保护边界；新增缓存适配器应提供原生命令、明确的目标绑定和隔离测试。新增自动化能力应显式说明触发、授权、保留规则和失败行为。

更多实现约束见 [SKILL.md](SKILL.md)、[清理规则](references/cleanup-rules.md) 和 [迭代成果规则](references/iteration-results.md)。
