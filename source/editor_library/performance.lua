-- Keep bounded caches for repeated GDI measurements and background blending.
local ffi = require('ffi')
local M = {}
function M.attach(shim, style)
    if shim._library_performance then return end
    shim._library_performance = true
    local text, labels, label_count = style.text, {}, 0
    style.text = function(value)
        local key = tostring(value)
        local found = labels[key]
        if found then return found end
        if label_count >= 4096 then labels, label_count = {}, 0 end
        local result = text(key)
        labels[key], label_count = result, label_count + 1
        return result
    end
    local measure, widths, count = shim.text_width, {}, 0
    shim.text_width = function(text, size, bold)
        local key = shim.lang() .. '|' .. math.max(6, math.floor(size+0.5)) .. '|' .. tostring(bold and true or false) .. '|' .. tostring(text)
        if widths[key] then return widths[key] end
        if count >= 4096 then widths, count = {}, 0 end
        local result = measure(text, size, bold)
        widths[key], count = result, count+1
        return result
    end
    -- Solid fills used to assign every pixel through Lua. Build one scanline
    -- and copy it through FFI; retain only the most recent color and width.
    local fill, row, row_key = shim.fill, nil, nil
    shim.fill = function(x0,y0,x1,y1,c)
        if (c[1] or 255) < 255 then return fill(x0,y0,x1,y1,c) end
        -- Let the shim apply its palette and surface image handling first.
        -- A one-line buffer uses exactly those same rendered pixels.
        x0,y0 = math.max(0,math.floor(x0+0.5)),math.max(0,math.floor(y0+0.5))
        x1,y1 = math.min(shim.w,math.floor(x1+0.5)),math.min(shim.h,math.floor(y1+0.5))
        if x1<=x0 or y1<=y0 then return end
        -- Background surfaces depend on position; preserve their renderer.
        if math.max(c[2],c[3],c[4])-math.min(c[2],c[3],c[4])<=3 and c[2]<=76 then
            return fill(x0,y0,x1,y1,c)
        end
        local key=table.concat({x1-x0,c[2],c[3],c[4]},':')
        if key~=row_key then
            fill(x0,y0,x1,y0+1,c)
            shim.flush()
            row=ffi.new('uint32_t[?]',x1-x0)
            ffi.copy(row,shim.bits+y0*shim.w+x0,(x1-x0)*4)
            row_key=key
        end
        for y=y0,y1-1 do ffi.copy(shim.bits+y*shim.w+x0,row,(x1-x0)*4) end
    end
    local surface, surfaces, total, dimensions = style.surface, {}, 0, ''
    style.surface = function(bits,w,h,x0,y0,x1,y1,c)
        if c[1]~=255 or math.max(c[2],c[3],c[4])-math.min(c[2],c[3],c[4])>3 or c[2]>76 or x1-x0<5 or y1-y0<5 then return false end
        if w*h*4 > 64*1024*1024 then return surface(bits,w,h,x0,y0,x1,y1,c) end
        local dim = w .. ':' .. h .. ':' .. style.background_opacity
        if dim ~= dimensions then surfaces,total,dimensions = {},0,dim end
        local key = c[2] .. ':' .. c[3] .. ':' .. c[4]
        local pixels = surfaces[key]
        if not pixels then
            if total+w*h*4 > 64*1024*1024 then surfaces,total = {},0 end
            pixels = ffi.new('uint32_t[?]',w*h)
            surface(pixels,w,h,0,0,w,h,c)
            surfaces[key],total = pixels,total+w*h*4
        end
        local bytes = (x1-x0)*4
        for y=y0,y1-1 do ffi.copy(bits+y*w+x0,pixels+y*w+x0,bytes) end
        return true
    end
end
return M
