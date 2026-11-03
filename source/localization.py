"""UI translations; imported names, paths, data values and diagnostic logs stay intact."""
import re
from localization_ru import RU

LANGUAGES = {'en': 'English', 'zh-CN': '简体中文', 'ru': 'Русский'}
_language = 'en'


def set_language(code):
    global _language
    _language = code if code in LANGUAGES else 'en'


def language():
    return _language


ZH = {
    'TOOL UPDATES': '工具更新',
    'GAME LOADER': '游戏加载器',
    'UPDATE/REPAIR built-in mods': '更新/修复内置模组',
    'Updates and repairs all three built-in mods for the current game. Run again after a game update or changing unlock categories.': '为当前游戏更新和修复全部三个内置模组。游戏更新或更改解锁类别后请再次运行。',
    'LOADERS': '加载器',
    'LOADERS DEPLOY FIRST': '加载器最先部署',
    'LOADERS DEPLOY LAST': '加载器最后部署',
    'Log font size': '日志字号',
    'ADVANCED CREATOR': '高级制作工具',
    'data mods + HellForge': '数据模组 + HellForge',
    'VISUAL & AUDIO MOD CREATOR': '视觉与音频模组制作',
    'OPEN VISUAL & AUDIO EDITOR': '打开视觉与音频编辑器',
    'Visual & Audio Mod Creator': '视觉与音频模组制作',
    'Stratagem Bounce Removed': '移除战备球弹跳', 'Consistent Vaulting': '稳定翻越',
    'Open mod ZIP / archive': '打开模组 ZIP / 归档', 'Replace from donor mod': '从其他模组替换',
    'Export mod ZIP': '导出模组 ZIP', 'Mod name': '模组名称', 'Search hash / type': '搜索哈希 / 类型',
    'Archive': '归档', 'Resource type': '资源类型', 'Resource hash': '资源哈希',
    'Main / stream / GPU bytes': '主文件 / 流 / GPU 字节数', 'Edited': '已修改', 'Yes': '是',
    'Export native asset bundle': '导出原生资源包', 'Import native asset bundle': '导入原生资源包',
    'Restore selected': '还原所选资源', 'Unsaved replacements': '未保存的替换',
    'Discard staged replacements?': '放弃暂存的替换？', 'Select a resource first.': '请先选择资源。',
    'Choose replacement resource': '选择替换资源', 'Use selected replacement': '使用所选替换资源',
    'Replacement staged. Export mod ZIP to save.': '替换已暂存。导出模组 ZIP 以保存。',
    'Native asset bundle exported.': '已导出原生资源包。', 'Open a source mod first.': '请先打开源模组。',
    'Mod exported': '模组已导出', 'Add this mod ZIP to the library?': '将此模组 ZIP 添加到模组库？',
    'Open a mod ZIP or game archive, browse texture and sound resources, replace native assets, and export a mod ZIP for the library.': '打开模组 ZIP 或游戏归档，浏览纹理和声音资源，替换原生资源并导出可导入模组库的 ZIP。',
    'MOD LIBRARY': '模组库', 'MERGE AND DEPLOY': '合并与部署', 'DATA DECODER': '数据解码器',
    'MOD CREATOR': '模组制作', '⚙  SETTINGS': '⚙  设置', 'LOG': '日志', 'ABOUT AND UPDATE': '关于与更新',
    'Mod Library': '模组库', 'Deploy & Purge': '部署与还原', 'Data Decoder': '数据解码器',
    'Mod Creator': '模组制作', 'Settings': '设置', 'Log': '日志', 'About and Update': '关于与更新',
    'Add any mods, merge and deploy them with one click': '添加任意模组，一键合并并部署。',
    'Write the merged pack to the game, or restore stock.': '将合并的模组安装到游戏中，或还原原始文件。',
    'Decode, edit and reseal .dl_bin data files, or repack Stingray archives.': '解码、编辑并重新封装 .dl_bin 数据，或重新打包 Stingray 归档。',
    'Loaders, editors and unlocks for your mod setup.': '管理加载器、编辑器和外观解锁功能。',
    'Language, desktop shortcut and appearance.': '语言、桌面快捷方式和外观设置。',
    'Everything the Laboratory did this session.': '查看本次运行的操作记录。',
    'ready': '就绪', 'data mods only\nno runtime hooks': '数据模组工具\n无需运行时挂钩',
    '▶  START GAME': '▶  启动游戏', '+ Add ZIP / 7Z': '+ 添加 ZIP / 7Z', '+ Add Folder': '+ 添加文件夹',
    'Remove': '移除', 'Options': '选项', 'Purge All Mods': '还原已部署模组',
    'View Mods Folder': '打开模组文件夹', 'Get Mods': '获取模组', 'Choose a mod website': '选择模组网站',
    'Download a mod, then use Add ZIP / 7Z or Add Folder in the library.': '下载模组后，在模组库中使用“添加 ZIP / 7Z”或“添加文件夹”。',
    'No web browser could be opened.': '无法打开网页浏览器。',
    'Priority: the top mod wins where two change the same value.': '优先级：多个模组修改相同数值时，靠上的模组优先。',
    'Drag cards into LOADERS, GAMEPLAY or VISUAL & AUDIO, including empty groups. Higher mods have priority within each group. Green ON includes a mod in the next installation; use Merge and Install All to deploy.': '将卡片拖入加载器、玩法或视觉与音频分类，包括空分类。分类内靠上的模组优先。绿色“开启”表示参与下次安装；点击“合并并安装全部”才会部署。',
    'Enable the parts of this mod to deploy:': '选择要部署的模组组件：', 'Select all': '全选', 'Clear all': '全部取消',
    'Save': '保存', 'Close': '关闭', 'Cancel': '取消', 'Browse': '浏览', 'Game folder': '游戏文件夹',
    'Stock: not captured': '原始快照：尚未保存', 'STOCK: ?': '原始快照：?',
    'MERGE and INSTALL ALL': '合并并安装全部', 'Capture Clean Game Files': '保存干净游戏快照',
    'Preview Deployment': '预览部署', 'Clean stock required': '需要干净的原始快照',
    'Capture clean game files before installing. Open the stock capture tools now?': '安装前请先保存干净游戏文件。现在打开快照工具吗？',
    'Choose your Helldivers 2 game folder in Merge and Deploy before continuing.': '请先在“合并与部署”中选择 Helldivers 2 游戏文件夹。',
    'Export Mod Library': '导出模组库', 'Import Library': '导入模组库', 'Verify Steam Files': '验证 Steam 文件',
    'Completely Purge Mod Library': '彻底清空模组库',
    'GAMEPLAY': '玩法', 'VISUAL & AUDIO': '视觉与音频',
    '●  ON  · click to disable': '●  开启 · 点击关闭', '●  OFF  · click to enable': '●  关闭 · 点击开启',
    '●  ON': '●  开启', '●  OFF': '●  关闭',
    'IMPORT TOOL UPDATES': '导入工具更新', 'CHECK CHEF FOR UPDATES': '检查 Chef 更新',
    'CHECK SHODAN FOR UPDATES': '检查 SHODAN 更新', 'IMPORT CCM UPDATE MANUALLY': '手动导入 CCM 更新',
    'IMPORT CHEF UPDATE MANUALLY': '手动导入 Chef 更新', 'GAME LOADERS': '游戏加载器',
    'ADD CHEF SHARED LOADER': '添加 Chef Shared Loader', 'SHODAN  /  STAT EDITOR': 'SHODAN / 属性编辑器',
    'OPEN SHODAN EDITOR': '打开 SHODAN 编辑器', 'CAPTURE GAME AS MOD': '将游戏修改保存为模组',
    'IMPORT EDIT PRESETS': '导入编辑预设', 'OPEN CAPTURE FOLDER': '打开捕获文件夹',
    'OPEN EDITOR PRESETS': '打开编辑器预设', 'COMBINED COMMUNITY MODS': 'Combined Community Mods',
    'OPEN CCM EDITOR': '打开 CCM 编辑器', 'IMPORT PRESETS': '导入预设', 'OPEN SAVED PRESETS': '打开已保存预设',
    'OPEN ARMORY PRESETS': '打开军械库预设', 'NATIVE GAME DATA EDITOR — WINDOWS / LINUX': '原生游戏数据编辑器 — Windows / Linux',
    'OPEN NATIVE EDITOR': '打开原生编辑器', 'HIDDEN CONTENT UNLOCKER': '隐藏外观解锁',
    'Include with Install All': '安装全部时包含此功能', 'Configure Unlock Categories': '选择解锁分类',
    'Choose cosmetic categories for the next Merge and Install All.': '选择下次合并安装时使用的外观分类。',
    'Colored B-01 Extra Padding (verifies native passive first)': '彩色 B-01 额外衬垫（先验证原生被动属性）',
    'Save Settings': '保存设置', 'Choose an archive or an extracted folder.': '选择压缩包或已解压的文件夹。',
    'Choose Archive': '选择压缩包', 'Choose Folder': '选择文件夹',
    'Check GitHub for Chef or SHODAN updates. Import a CCM update from a ZIP or extracted folder; renamed download folders are fine.': '从 GitHub 检查 Chef 或 SHODAN 更新。CCM 更新可从 ZIP 或已解压文件夹手动导入，下载文件夹改名后仍可使用。',
    'Chef Shared Loader runs compatible Lua mods. Add the bundled version or import an update, then Deploy to install.': 'Chef Shared Loader 用于运行兼容的 Lua 模组。添加内置版本或导入更新，然后部署到游戏。',
    "Chef Shared Loader - full Lua 5.1 runtime: side-by-side mods, crash guard, sandbox, F9 menu. Deploy it last. Use when your mods need Chef's runtime.": 'Chef Shared Loader 提供 Lua 5.1 运行环境、多个模组共存、崩溃保护、沙盒和 F9 菜单。其启动文件最后部署，适用于需要 Chef 的模组。',
    'SHODAN Editor for weapons, vehicles, stratagems, armour passives and more. It opens in its own window; press Install there to write, then capture the result as a mod here.': 'SHODAN 可编辑武器、载具、战略配备和护甲被动等数据。它会打开独立窗口；先在编辑器中安装修改，再在此捕获为模组。',
    'Another choice of an editor, supports full screen mode.': '另一个编辑器选项，支持全屏模式。',
    'Browse the game file database, search entries and edit named properties from the matching type library and reference layouts. Coverage Report identifies unresolved names; those properties stay read-only. SHODAN/CCM remain separate tools.': '浏览游戏数据库、搜索条目，并借助匹配的类型库编辑已识别属性。覆盖率报告列出未识别项，这些属性保持只读。SHODAN 和 CCM 是独立工具。',
    'HD REMIX 0.5.2 cosmetic profiles. Generated from captured stock; supported game build 26088801 is checked before deployment. Ship/Stratagem Hero changes from the standalone installer are not included. Purge restores the managed deployment.': '使用 HD REMIX 0.5.2 外观配置，从干净快照生成。部署前检查支持的游戏构建 26088801。不包含独立安装器的舰船或战略英雄修改。还原功能会撤销本应用管理的部署。',
    'Capture Game as Mod writes two ZIPs: a portable file mod for file-based managers, and an Arsenal data pack that bundles the YAO loader so Arsenal, HD2 Mod Manager and DDMM can deploy it as patch files. The Arsenal pack needs launch, exit and launch again to apply.': '“将游戏修改保存为模组”会生成两个 ZIP：普通文件模组，以及附带 YAO 加载器的 Arsenal 数据包。Arsenal、HD2 Mod Manager 和 DDMM 可部署该补丁包；首次使用需启动游戏、正常退出，再次启动。',
    'Language': '语言', 'GENERATE NEW DESKTOP SHORTCUT': '重新生成桌面快捷方式',
    'Presets': '主题预设', 'Accent': '强调色', 'Custom colors': '自定义颜色', 'Font size': '字号',
    'Save theme': '保存主题', 'Reset': '重置', 'Background': '背景', 'Panel': '面板', 'Text': '文字',
    'Clear Log': '清空日志', 'Copy Log': '复制日志', 'Log copied to clipboard.': '日志已复制到剪贴板。',
    'Guide section': '指南章节', 'Find next': '查找下一个', 'Check for Updates': '检查更新',
    'Release Downloads': '下载发布版本', 'Open App Data': '打开应用数据', 'Restart to Update': '重启并更新',
    'Check for app updates every time the app starts': '每次启动应用时检查更新',
    'RESTART THE APP': '重启应用',
    'Changing the language automatically restarts the app.': '更改语言后会自动重启应用。',
    'Checking for a newer stable release…': '正在检查稳定版本更新…', 'Starting update download…': '正在开始下载更新…',
    'Could not check for updates. Try again or use Release Downloads.': '检查更新失败。请稍后重试，或下载完整发布版本。',
    'Use the launcher for in-app installation, or choose Release Downloads.': '请通过启动器使用应用内更新，或下载完整发布版本。',
    'Update failed. Your current version is still active; see Log.': '更新失败，当前版本仍有效。请查看日志。',
    'Support is completely optional. ModDiver Lab will forever be free and open-source.': '支持完全自愿。ModDiver Lab 将永久免费并开源。',
    'SUPPORT': '支持项目', 'Thank you!': '谢谢！', 'Which one works best for you?': '哪种支持方式最适合您？',
    'Editor not supported on Linux yet': '此外部编辑器暂不支持 Linux',
    'Desktop shortcut created.': '桌面快捷方式已创建。',
    'Start with run-linux.sh to create a desktop shortcut.': '请通过 run-linux.sh 启动应用后再创建桌面快捷方式。',
    'Desktop shortcut created. Your desktop may ask you to allow launching it.': '桌面快捷方式已创建。桌面环境可能要求你允许启动它。',
    'Start the app using ModDiver Laboratory.exe to create its desktop shortcut.': '请通过 ModDiver Laboratory.exe 启动应用后再创建快捷方式。',
    'Wait for the current operation to finish before closing.': '请等待当前操作完成后再关闭。',
    'Close the external editor before closing or restarting Laboratory.': '关闭或重启本应用前，请先关闭外部编辑器。',
    'An editor has unsaved changes. Discard them and close?': '编辑器有未保存的修改。放弃修改并关闭吗？',
    'An update operation is already in progress.': '更新操作正在进行中。',
    'Finish the current operation, then check for updates again.': '请等待当前操作完成后再检查更新。',
    'OPEN FILE / ARCHIVE': '打开文件 / 归档', 'EXPORT REPACKED FILE': '导出重打包文件', 'GUIDE': '指南',
    'Open a sealed .dl_bin data file or a Stingray archive / .patch_N file.': '打开封装的 .dl_bin 数据文件或 Stingray 归档 / .patch_N 补丁。',
    'RESOURCE HASH': '资源哈希', 'TYPE HASH': '类型哈希', 'BYTES': '字节数',
    'Select a resource.': '请选择资源。', 'Apply Edit': '应用编辑', 'Export Payload': '导出资源数据',
    'Import Replacement': '导入替换数据', 'Restore Original': '还原原始数据', 'Working…': '处理中…', 'Close Guide': '关闭指南',
    '.dl_bin files decode to LDLD blocks. Numeric views show 4-byte values at block-relative offsets; field names are not inferred. Keep block lengths unchanged. Export verifies and reseals data files; archive exports include sidecars.': '.dl_bin 文件可解码为 LDLD 数据块。数值视图按块内偏移显示 4 字节数值，不推断字段名。请保持数据块长度不变。导出时验证并重新封装数据；归档导出包含配套文件。',
    'Export cancelled; staged edits are still available.': '导出已取消，暂存修改仍保留。',
    'Native Game Data Editor': '原生游戏数据编辑器', 'Open Game Database': '打开游戏数据库', 'Open Data File': '打开数据文件',
    'Load Type Library': '加载类型库', 'Export Edited File': '导出编辑文件', 'Rename Entry': '重命名条目', 'Coverage Report': '覆盖率报告',
    'Load the game database to browse files, entries and verified named properties.': '加载游戏数据库后可浏览文件、条目及已验证属性。',
    'Schema footer export (experimental)': '追加校验填充导出（实验性）',
    'GAME DATA FILES': '游戏数据文件', 'ENTRIES / SEARCH ABOVE': '条目 / 在上方搜索', 'PROPERTY': '属性', 'VALUE': '数值', 'MEANING / STATUS': '含义 / 状态',
    'Previous': '上一页', 'Next': '下一页', 'Loading / verifying…': '加载 / 验证中…', 'Save change': '保存修改',
    'Type library loaded. Open a data file from the same game version.': '类型库已加载。请打开相同游戏版本的数据文件。',
    'Double-click a verified property to edit. Unresolved names, references and unsupported layouts are read-only. Custom entry names change display labels only. Export saves a new verified file, not the installed game.': '双击已验证的属性进行编辑。未识别名称、引用和不支持的布局保持只读。自定义名称仅改变显示标签。导出会创建新文件，不会直接修改已安装游戏。',
    'Open Game Armor': '打开游戏护甲数据', 'Open Game Passives': '打开游戏被动属性',
    'Correcting hash and resealing with the portable engine…': '正在校正哈希并重新封装…',
    'Changes staged. Export Edited File to save a mod copy.': '修改已暂存。请导出编辑文件以保存模组副本。',
    'Named armour-kit availability/passive fields and passive effect values. Double-click a field to edit.': '编辑已识别的护甲可用性、被动属性和效果数值。双击字段进行编辑。',
    'Export preserves the input and verifies the content hash. Add the exported file folder to Mod Library to deploy. This native editor covers armour kits and passive effects; it is not the full SHODAN/CCM feature set.': '导出保留输入文件并验证内容哈希。将导出文件所在文件夹添加到模组库后即可部署。此编辑器支持护甲与被动效果，功能范围与 SHODAN/CCM 不同。',
    'Armour passives': '护甲被动', 'Passive': '被动属性', 'Fields': '字段', 'Weapons': '武器', 'Weapon': '武器',
    'Slot': '插槽', 'Damage': '伤害', 'Damage id': '伤害 ID', 'Values': '数值', 'RELOAD': '重新加载',
    'Value': '数值', 'Current': '当前值', 'Field': '字段', 'Name': '名称',
    'SAVE PASSIVES': '保存被动属性', 'SAVE WEAPONS': '保存武器', 'SAVE DAMAGE': '保存伤害',
    'Double-click a value, then SAVE PASSIVES.': '双击数值修改，然后保存被动属性。',
    'Double-click a value, then SAVE WEAPONS.': '双击数值修改，然后保存武器。',
    'Double-click a value, then SAVE DAMAGE.': '双击数值修改，然后保存伤害。',
}

from localization_extra import ZH_EXTRA, RU_EXTRA
ZH.update(ZH_EXTRA)
RU.update(RU_EXTRA)

PATTERNS = (
    (r'(\d+) mods', lambda m: m[1] + ' 个模组'),
    (r'· DEPLOYED (\d+)', lambda m: '· 已部署 ' + m[1]),
    (r'(\d+)  /  BUILT-IN MOD', lambda m: m[1] + ' / 内置模组'),
    (r'Stock: (\d+) files', lambda m: '原始快照：' + m[1] + ' 个文件'),
    (r'   Deployed: (\d+)', lambda m: '   已部署：' + m[1]),
    (r'STOCK (\d+)  DEPLOYED (\d+)', lambda m: f'快照 {m[1]}  已部署 {m[2]}'),
    (r'(LOADERS|GAMEPLAY|VISUAL & AUDIO)  \((\d+)\)', lambda m: ZH[m[1]] + '  (' + m[2] + ')'),
    (r'Version (.+) is available\.', lambda m: '版本 ' + m[1] + ' 可用。'),
    (r'Version (.+) installed\. Restart when ready\.', lambda m: '版本 ' + m[1] + ' 已安装。请在准备好后重启。'),
    (r'You have the latest available stable version \(v(.+)\)\.', lambda m: '当前已是最新稳定版 (v' + m[1] + ')。'),
    (r'ModDiver Laboratory is up to date! \(v(.+)\)\.', lambda m: 'ModDiver Laboratory 已是最新版 (v' + m[1] + ')。'),
)


def tr(text):
    if _language == 'ru' and isinstance(text, str):
        if text in RU:
            return RU[text]
        for pattern, replacement in RU_PATTERNS:
            match = re.fullmatch(pattern, text)
            if match:
                return replacement(match)
        return text
    if _language != 'zh-CN' or not isinstance(text, str):
        return text
    if text in ZH:
        return ZH[text]
    for pattern, replacement in PATTERNS:
        match = re.fullmatch(pattern, text)
        if match:
            return replacement(match)
    return text


RU_PATTERNS = (
    (r'(\d+) mods', lambda m: m[1] + ' модов'),
    (r'· DEPLOYED (\d+)', lambda m: '· УСТАНОВЛЕНО ' + m[1]),
    (r'(\d+)  /  BUILT-IN MOD', lambda m: m[1] + ' / ВСТРОЕННЫЙ МОД'),
    (r'Stock: (\d+) files', lambda m: 'Оригиналы: ' + m[1] + ' файлов'),
    (r'   Deployed: (\d+)', lambda m: '   Установлено: ' + m[1]),
    (r'STOCK (\d+)  DEPLOYED (\d+)', lambda m: f'ОРИГИНАЛЫ {m[1]}  УСТАНОВЛЕНО {m[2]}'),
    (r'(LOADERS|GAMEPLAY|VISUAL & AUDIO)  \((\d+)\)', lambda m: RU[m[1]] + '  (' + m[2] + ')'),
    (r'Version (.+) is available\.', lambda m: 'Доступна версия ' + m[1] + '.'),
    (r'Version (.+) installed\. Restart when ready\.', lambda m: 'Версия ' + m[1] + ' установлена. Перезапустите приложение.'),
    (r'You have the latest available stable version \(v(.+)\)\.', lambda m: 'Установлена последняя стабильная версия (v' + m[1] + ').'),
    (r'ModDiver Laboratory is up to date! \(v(.+)\)\.', lambda m: 'ModDiver Laboratory обновлена! (v' + m[1] + ').'),
)
