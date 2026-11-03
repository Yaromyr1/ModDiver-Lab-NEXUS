-- Library-only output. This module never writes to the selected game directory.
local ffi = require('ffi')
local M = {}
local function required(name)
    local value = os.getenv(name)
    assert(value and value ~= '', 'Open ModDiverEditor from ModDiver Laboratory: missing ' .. name)
    return value
end
local baseline = required('MODDIVER_EDITOR_BASELINE')
local output = required('MODDIVER_EDITOR_OUTPUT')
M.worker = os.getenv('MODDIVER_EDITOR_WORKER') == '1'
local revision = (tonumber(os.getenv('MODDIVER_EDITOR_REVISION')) or 1) - 1
local progress_checked, progress_value = -1, nil
function M.report(phase, done, total)
    if not M.worker then return end
    local target = tonumber(os.getenv('MODDIVER_EDITOR_REVISION')) or revision+1
    local text = target .. '\n' .. phase:gsub('[\r\n]', ' ') .. '\n' .. (done or 0) .. '\n' .. (total or 0)
    local f = io.open(output .. '/progress.new', 'wb')
    if not f then return end -- Progress must never invalidate a mod build.
    local ok = f:write(text); f:close()
    if ok then ffi.C.MoveFileExA(output .. '/progress.new', output .. '/progress.txt', 9) end
end
function M.build_progress(I)
    if not M.building then return nil end
    if os.time() ~= progress_checked then
        progress_checked = os.time()
        local text = I.read(output .. '/progress.txt') or ''
        local number, phase, done, total = text:match('^(%d+)\n([^\n]+)\n(%d+)\n(%d+)$')
        if tonumber(number) == revision then
            progress_value = {phase=phase, done=tonumber(done), total=tonumber(total), key=text}
        end
    end
    return progress_value
end
function M.attach(I, S, FP)
    function I.originals(game)
        local G = require('gamedata')
        local dll = assert(I.read(game .. '/game.dll'), 'Cannot read game.dll')
        local out, count = {}, 0
        local names = I.list_files(baseline, 'generated_*.dl_bin')
        if M.progress then M.progress('Validating clean game data', 0, #names) end
        for _, name in ipairs(names) do
            out[name] = assert(I.read(baseline .. '/' .. name), 'Missing stock file: ' .. name)
            local plain, size = G.open_sealed(out[name])
            assert(plain, 'Invalid clean stock file: ' .. name)
            local clean = G.game_dll_has(dll, G.murmur64(plain, size)) and not G.clear_correction(plain, size)
            G.free(plain)
            assert(clean, 'Stock is modified or belongs to another game build: ' .. name .. '. Verify and capture clean stock in Laboratory Settings.')
            count = count + 1
            if M.progress then M.progress('Validating clean game data', count, #names) end
        end
        assert(count > 0, 'Clean stock baseline is empty')
        return out, {}, {}, count
    end
    local function blocked() error('Deploy editor changes from the Mod Library using Merge and Install All.') end
    I.write_files, I.write_patch, S.sync, FP.sync = blocked, blocked, blocked, blocked
    I.patch_installed = function() return nil end
end
local checked, message = -1, nil
function M.status(I)
    if os.time() ~= checked then
        checked = os.time()
        local text = I.read(output .. '/status.txt') or ''
        local number, body = text:match('^(%d+)\n(.*)')
        message = tonumber(number) == revision and body or nil
        if message and (message:find('Library updated',1,true) or message:find('failed',1,true)) then
            M.building = false
        end
    end
    return message
end
function M.request(I, finish)
    revision = revision + 1
    message, checked = nil, -1
    local folder = output .. '/../requests/' .. revision
    local settings = folder .. '/project/ModDiver/StatEditor'
    I.mkdirs(settings)
    -- Snapshot only editable settings. Backups and installed game data are excluded.
    for _, pattern in ipairs({'*.txt', '*.ini'}) do
        for _, name in ipairs(I.list_files(I.home, pattern)) do
            if name ~= 'installed.txt' and name ~= 'game folder.txt' then
                local bytes = assert(I.read(I.home .. '/' .. name), 'Cannot snapshot ' .. name)
                local f = assert(io.open(settings .. '/' .. name, 'wb'))
                assert(f:write(bytes)); assert(f:close())
            end
        end
    end
    local f = assert(io.open(folder .. '/request.new', 'wb'))
    assert(f:write('MODDIVER_EDITOR_REQUEST_1\n' .. (finish and 'return-to-library' or 'background') .. '\n'))
    assert(f:close())
    assert(ffi.C.MoveFileExA(folder .. '/request.new', folder .. '/request.txt', 9) ~= 0, 'Cannot queue library build')
    M.building, progress_checked = true, -1
    progress_value = {phase='Preparing your saved edits', done=0, total=0, key='queued:' .. revision}
    return revision
end
function M.publish(I, writes, physics, base, steering, fp, S, FP)
    local files = {}
    for name, bytes in pairs(writes) do files['data/game/' .. name] = bytes end
    local slot = 0
    local function archive(stem, bytes, gpu, stream)
        local path = 'data/' .. stem .. '.patch_' .. slot
        files[path], files[path .. '.gpu_resources'], files[path .. '.stream'] = bytes, gpu or '', stream or ''
        slot = slot + 1
    end
    if physics then archive(base, physics) end
    if steering then
        local source, why = S.source()
        assert(source, why)
        archive('9ba626afa44a3aa3', source.main, source.gpu, source.stream)
    end
    if fp then
        local payload, why = FP.library_payload()
        assert(payload, why)
        for _, item in ipairs(payload) do archive('9ba626afa44a3aa3', item[1], item[2], item[3]) end
    end
    revision = revision + 1
    message, checked = nil, -1
    local folder = output .. '/' .. revision
    I.mkdirs(folder .. '/data/game')
    local names = {}
    for name in pairs(files) do names[#names + 1] = name end
    table.sort(names)
    local lines = {'MODDIVER_EDITOR_1'}
    M.report('Writing and verifying mod files', 0, #names)
    for index, name in ipairs(names) do
        local path = folder .. '/' .. name
        local f = assert(io.open(path, 'wb'))
        assert(f:write(files[name])); assert(f:close())
        assert(I.read(path) == files[name], 'Export read-back failed: ' .. name)
        lines[#lines + 1] = name .. '\t' .. #files[name]
        M.report('Writing and verifying mod files', index, #names)
    end
    local pending = folder .. '/ready.new'
    local f = assert(io.open(pending, 'wb'))
    assert(f:write(table.concat(lines, '\n') .. '\n')); assert(f:close())
    assert(ffi.C.MoveFileExA(pending, folder .. '/ready.txt', 9) ~= 0, 'Cannot finish library export')
    M.report('Adding your mod to the library', nil, nil)
    return #names
end
return M
