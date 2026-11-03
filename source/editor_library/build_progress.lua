-- Visible progress in the interactive editor while its separate worker builds.
local M = {}
function M.paint(shim, progress, centered, now)
    if not progress then return end
    local w = math.min(580, shim.w-48)
    local h = 170
    local x = centered and (shim.w-w)/2 or shim.w-w-24
    local y = centered and (shim.h-h)/2 or 62
    local gold, white, muted = {255,255,213,0}, {255,238,238,238}, {255,170,170,170}
    if centered then shim.fill(0,0,shim.w,shim.h,{150,0,0,0}) end
    shim.fill(x+5,y+5,x+w+5,y+h+5,{255,12,12,12})
    shim.fill(x,y,x+w,y+h,{255,26,26,26})
    shim.fill(x,y,x+w,y+2,gold)
    shim.flush()
    shim.text('Creating your mod',x+24,y+38,22,white,true)
    shim.text(progress.phase,x+24,y+68,15,muted)
    local left,right,top = x+24,x+w-24,y+92
    shim.fill(left,top,right,top+5,{255,62,62,62})
    local caption = 'Working in the background'
    if progress.total > 0 then
        local fraction = math.max(0,math.min(1,progress.done/progress.total))
        shim.fill(left,top,left+(right-left)*fraction,top+5,gold)
        caption = string.format('%d%% of this stage   ·   %d / %d files',math.floor(fraction*100),progress.done,progress.total)
    else
        local span=(right-left)*0.2
        local offset=((now or 0)*0.45)%1
        local at=left+(right-left-span)*offset
        shim.fill(at,top,at+span,top+5,gold)
    end
    shim.flush()
    shim.text(caption,x+24,y+124,14,muted)
    shim.text(centered and 'The editor will close when your mod is ready.' or 'You can keep editing. Your game files are unchanged.',x+24,y+150,12,muted)
end
return M
