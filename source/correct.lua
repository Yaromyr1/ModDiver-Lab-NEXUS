-- ModDiver Laboratory hash corrector: corrects a merged plaintext to the stock content hash and seals it.
-- Globals set by lua_runner.py: YAO_STOCK, YAO_CAND, YAO_OUT, YAO_FLOATS
local APP = os.getenv('YAO_SHODAN_APP')
package.path = APP .. '?.lua;' .. package.path
local ffi = require('ffi')
local G = require('gamedata')

local function read(p)
    local f = io.open(p, 'rb'); if not f then return nil end
    local s = f:read('*a'); f:close(); return s
end

local stock = assert(read(rawget(_G, 'YAO_STOCK')), 'no stock')
local cand = assert(read(rawget(_G, 'YAO_CAND')), 'no cand')
local out = rawget(_G, 'YAO_OUT')
local floats = {}
for v in tostring(rawget(_G, 'YAO_FLOATS') or ''):gmatch('([^,]+)') do
    local n = tonumber(v); if n then floats[#floats + 1] = n end
end

local p = G.alloc(#stock)
ffi.copy(p, stock, #stock)
local target = G.murmur64(p, #stock)

local q = G.alloc(#cand)
ffi.copy(q, cand, #cand)
G.clear_correction(q, #cand)
local ok, err = G.correct(q, #cand, target, floats, function(s) print('LOG ' .. tostring(s)) end)
if not ok then print('ERR ' .. tostring(err)); os.exit(1) end
local sealed = G.seal(q, #cand)
local f = assert(io.open(out, 'wb')); f:write(sealed); f:close()
print('OK ' .. #sealed)
