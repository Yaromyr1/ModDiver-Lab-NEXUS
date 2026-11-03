-- YAO native editor bridge: per-weapon handling + damage, following the SHODAN chain.
-- Entities (T_WEAPON/T_ROUNDS/T_FIRE) + projectile settings (T_PROJECTILE) + damage settings (T_DAMAGE).
-- Globals: YAO_MODE (dump|apply), YAO_FILE, YAO_PROJ, YAO_DMG, YAO_OUT, YAO_STOCK, YAO_EDITS
local APP = os.getenv('YAO_SHODAN_APP')
package.path = APP .. '?.lua;' .. package.path
local ffi = require('ffi')
local G = require('gamedata')

local T_WEAPON, WSTRIDE = 0x88E4DBB1, 1232
local T_ROUNDS, RSTRIDE = 0x66081072, 136
local T_FIRE, FSTRIDE = 0x45171B68, 616
local T_PROJECTILE, PSTRIDE = 0xBD4042C2, 272
local T_DAMAGE, DSTRIDE = 0xE0A72CF0, 76

local W_FIELDS = { { 'recoil_h', 0 }, { 'recoil_v', 4 }, { 'recoil_ch', 28 }, { 'recoil_cv', 32 },
                   { 'spread_h', 84 }, { 'spread_v', 88 }, { 'sway', 104 }, { 'ergonomics', 356 } }
local D_FIELDS = { { 'damage', 4 }, { 'durable', 8 }, { 'ap_direct', 12 }, { 'ap_slight', 16 },
                   { 'ap_large', 20 }, { 'ap_extreme', 24 }, { 'demolition', 28 }, { 'stagger', 32 }, { 'push', 36 } }

local function read(p)
    if not p or p == '' then return nil end
    local f = io.open(p, 'rb'); if not f then return nil end
    local s = f:read('*a'); f:close(); return s
end
local function u32(buf, o) return ffi.cast('uint32_t *', buf + o)[0] end
local function f32(buf, o) return ffi.cast('float *', buf + o)[0] end
local function key64(buf, at) return string.format('%016X', ffi.cast('uint64_t *', buf + at)[0]) end

local function open_file(name)
    local s = read(rawget(_G, name))
    if not s then return nil, 0 end
    local p, n = G.open_sealed(s)
    return p, n
end

local ep, en = open_file('YAO_FILE')
assert(ep, 'entities file missing')
local pp, pn = open_file('YAO_PROJ')
local dp, dn = open_file('YAO_DMG')

local function rows(buf, size, typ, stride)
    local out = {}
    if not buf then return out end
    for _, h in ipairs(G.headers(buf, size)) do
        if h.type == typ and h.size >= stride then
            for i = 0, math.floor(h.size / stride) - 1 do out[#out + 1] = h.at + 24 + i * stride end
        end
    end
    return out
end

local function find64(buf, size, typ, stride, key)
    for _, at in ipairs(rows(buf, size, typ, stride)) do
        if key64(buf, at) == key then return at end
    end
end

local function find32(buf, size, typ, stride, want)
    for _, at in ipairs(rows(buf, size, typ, stride)) do
        if u32(buf, at) == want then return at end
    end
end

-- weapon key -> rounds(+64) or fire(+0) -> projectile id -> projectile(+60) -> damage id -> damage row
local function weapon_damage(wkey)
    if not (pp and dp) then return nil end
    local at = find64(ep, en, T_ROUNDS, RSTRIDE, wkey)
    local pid = at and u32(ep, at + 64) or 0
    if pid == 0 then
        at = find64(ep, en, T_FIRE, FSTRIDE, wkey)
        pid = at and u32(ep, at + 0) or 0
    end
    if pid == 0 then return nil end
    local prow = find32(pp, pn, T_PROJECTILE, PSTRIDE, pid)
    if not prow then return nil end
    local did = u32(pp, prow + 60)
    if did == 0 then return nil end
    return find32(dp, dn, T_DAMAGE, DSTRIDE, did), did
end

local mode = rawget(_G, 'YAO_MODE')
if mode == 'dump' then
    local lines = {}
    for _, at in ipairs(rows(ep, en, T_WEAPON, WSTRIDE)) do
        local wkey = key64(ep, at)
        for _, f in ipairs(W_FIELDS) do
            lines[#lines + 1] = string.format('W %s %s %.9g', wkey, f[1], f32(ep, at + f[2]))
        end
        local drow, did = weapon_damage(wkey)
        if drow then
            for _, f in ipairs(D_FIELDS) do
                lines[#lines + 1] = string.format('D %s %08X %s %.9g', wkey, did, f[1], f32(dp, drow + f[2]))
            end
        end
    end
    local f = assert(io.open(rawget(_G, 'YAO_OUT'), 'wb')); f:write(table.concat(lines, '\n')); f:close()
    print('OK dump ' .. #lines)
else
    local touched_damage = false
    for line in (read(rawget(_G, 'YAO_EDITS')) or ''):gmatch('[^\r\n]+') do
        local dkey, did, dfield, dval = line:match('^D%s+(%w+)%s+(%x+)%s+(%a[%w_]*)%s+([%d%.eE%+%-]+)$')
        local kind, wkey, field, val = line:match('^(%a)%s+(%w+)%s+(%a[%w_]*)%s+([%d%.eE%+%-]+)$')
        if dkey then
            local drow = find32(dp, dn, T_DAMAGE, DSTRIDE, tonumber(did, 16))
            if drow then
                touched_damage = true
                for _, f in ipairs(D_FIELDS) do
                    if f[1] == dfield then ffi.cast('float *', dp + drow + f[2])[0] = tonumber(dval) end
                end
            end
        elseif kind == 'W' then
            for _, at in ipairs(rows(ep, en, T_WEAPON, WSTRIDE)) do
                if key64(ep, at) == wkey then
                    for _, f in ipairs(W_FIELDS) do
                        if f[1] == field then ffi.cast('float *', ep + at + f[2])[0] = tonumber(val) end
                    end
                end
            end
        end
    end
    local function seal_write(buf, size, stock_name, out_name)
        local stock = read(rawget(_G, stock_name))
        local target
        if stock then
            local sp, sn = G.open_sealed(stock)
            target = G.murmur64(sp, sn); G.free(sp)
        else
            target = G.murmur64(buf, size)
        end
        G.clear_correction(buf, size)
        local ok, err = G.correct(buf, size, target, {}, function(s) print('LOG ' .. tostring(s)) end)
        if not ok then print('ERR ' .. tostring(err)); os.exit(1) end
        local sealed = G.seal(buf, size)
        local f = assert(io.open(out_name, 'wb')); f:write(sealed); f:close()
        print('OK seal ' .. #sealed)
    end
    seal_write(ep, en, 'YAO_STOCK', rawget(_G, 'YAO_OUT'))
    if touched_damage then seal_write(dp, dn, 'YAO_STOCK_DMG', rawget(_G, 'YAO_OUT2')) end
    print('OK apply')
end
