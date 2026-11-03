-- YAO native editor bridge: armour passives (LDLD type 0x63CE0FEB).
-- Globals from editor_runner.py: YAO_MODE (dump|apply), YAO_FILE, YAO_OUT, YAO_STOCK, YAO_EDITS
local APP = os.getenv('YAO_SHODAN_APP')
package.path = APP .. '?.lua;' .. package.path
local ffi = require('ffi')
local G = require('gamedata')
local PASSIVE = 0x63CE0FEB
local NONE = 0xFFFFFFFFFFFFFFFFULL

local function read(p)
    local f = io.open(p, 'rb'); if not f then return nil end
    local s = f:read('*a'); f:close(); return s
end

local function u32(p, o) return ffi.cast('uint32_t *', p + o)[0] end
local function f32(p, o) return ffi.cast('float *', p + o)[0] end

local cipher = assert(read(rawget(_G, 'YAO_FILE')), 'no file')
local mode = rawget(_G, 'YAO_MODE')
local p, n = G.open_sealed(cipher)
assert(p, 'open failed')
local hs = G.headers(p, n)

-- every armour passive block: payload at at+24, mods at +56 (16 bytes), stats after (12 bytes)
local function passives()
    local out = {}
    for _, h in ipairs(hs) do
        if h.type == PASSIVE and h.size >= 56 then
            local P = h.at + 24
            local mc = u32(p, P + 24)
            local sc = u32(p, P + 40)
            local so = tonumber(ffi.cast('uint64_t *', p + P + 32)[0])
            if mc <= 4096 and sc <= 4096 then out[#out + 1] = { P = P, id = u32(p, P), mc = mc, sc = sc, so = so } end
        end
    end
    return out
end

if mode == 'dump' then
    local lines = {}
    for _, b in ipairs(passives()) do
        lines[#lines + 1] = string.format('P %d %d', b.id, b.mc + b.sc)
        for k = 0, b.mc - 1 do
            local rec = b.P + 56 + k * 16
            lines[#lines + 1] = string.format('M %d %d %.9g', b.id, u32(p, rec), f32(p, rec + 8))
        end
        if b.sc > 0 and b.so ~= 0xFFFFFFFFFFFFFFFF then
            for k = 0, b.sc - 1 do
                local rec = b.P + b.so + k * 12
                lines[#lines + 1] = string.format('S %d %d %.9g', b.id, u32(p, rec), f32(p, rec + 4))
            end
        end
    end
    local f = assert(io.open(rawget(_G, 'YAO_OUT'), 'wb'))
    f:write(table.concat(lines, '\n')); f:close()
    print('OK dump ' .. #lines)
else
    for line in (read(rawget(_G, 'YAO_EDITS')) or ''):gmatch('[^\r\n]+') do
        local kind, pid, mid, val = line:match('^(%a)%s+(%d+)%s+(%d+)%s+([%d%.eE%+%-]+)$')
        if kind then
            for _, b in ipairs(passives()) do
                if b.id == tonumber(pid) then
                    if kind == 'M' then
                        for k = 0, b.mc - 1 do
                            local rec = b.P + 56 + k * 16
                            if u32(p, rec) == tonumber(mid) then ffi.cast('float *', p + rec + 8)[0] = tonumber(val) end
                        end
                    elseif kind == 'S' and b.sc > 0 and b.so ~= 0xFFFFFFFFFFFFFFFF then
                        for k = 0, b.sc - 1 do
                            local rec = b.P + b.so + k * 12
                            if u32(p, rec) == tonumber(mid) then ffi.cast('float *', p + rec + 4)[0] = tonumber(val) end
                        end
                    end
                end
            end
        end
    end
    local stock = read(rawget(_G, 'YAO_STOCK'))
    local target
    if stock then
        local sp, sn = G.open_sealed(stock)
        assert(sp, 'stock open failed')
        target = G.murmur64(sp, sn)
        G.free(sp)
    else
        target = G.murmur64(p, n)
    end
    G.clear_correction(p, n)
    local ok, err = G.correct(p, n, target, {}, function(s) print('LOG ' .. tostring(s)) end)
    if not ok then print('ERR ' .. tostring(err)); os.exit(1) end
    local sealed = G.seal(p, n)
    local f = assert(io.open(rawget(_G, 'YAO_OUT'), 'wb')); f:write(sealed); f:close()
    print('OK apply ' .. #sealed)
end
