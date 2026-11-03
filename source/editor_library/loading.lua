-- File counts describe measured stage work, never an estimated overall percent.
local M = {}
function M.attach(shim, worker)
    local last = 0
    local view = {}
    function view.show(label, done, total)
        if worker then return end
        local now = os.clock()
        if done and done > 0 and done < total and now-last < 0.05 then return end
        last = now
        assert(shim.pump(), 'Editor closed while loading')
        local w = math.min(640, shim.w*0.7)
        local x, y = (shim.w-w)/2, shim.h*0.46
        local gold, muted = {255,255,213,0}, {255,170,170,170}
        shim.fill(0,0,shim.w,shim.h,{255,20,20,20})
        shim.text('ModDiverEditor',x,y-58,30,gold,true)
        shim.text(label,x,y-18,17,muted)
        shim.fill(x,y,x+w,y+6,{255,62,62,62})
        if total and total > 0 then
            local fraction = math.max(0,math.min(1,done/total))
            shim.fill(x,y,x+w*fraction,y+6,gold)
            shim.text(string.format('%d%%   ·   %d / %d files',math.floor(fraction*100),done,total),x,y+38,15,muted)
        else
            shim.text('Please wait',x,y+38,15,muted)
        end
        shim.present()
    end
    return view
end
return M
