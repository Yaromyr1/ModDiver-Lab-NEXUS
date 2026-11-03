    -- The visible editor saves snapshots; a separate hidden worker builds them.
    local function signature()
        local f, v, h = C.signatures()
        return table.concat({tostring(state.writes), f, v, h, tostring(FP.enabled())}, '|')
    end
    local last_seen, last_built, changed_at, attempted = nil, nil, clock(), nil
    local closing = false
    local exit_requested, finish_requested = false, false
    local removal_open, removal_down = false, false
    paint_progress = function()
        require('library_build_progress').paint(shim, Library.build_progress(I), finish_requested, clock())
    end
    local function build()
        if not closing then busy('Building library mod...') end
        C.flush()
        C.reload()
        local ok, result = xpcall(function()
            Library.report('Preparing gameplay changes', nil, nil)
            -- Validate optional assets before allocating data build buffers.
            local map = require('hellpod').settings().map_steering
            local fp = FP.enabled()
            if map then local src, why = S.source(); assert(src, why) end
            if fp then local src, why = FP.library_payload(); assert(src, why) end
            local physics
            if rawget(_G, 'SHODAN_PHYSICS') then physics = V.patch() end
            local changes = C.diff(D, G, log, state.apex_stand_shoot and state.apex_stand_shoot())
            Library.report('Applying saved stat edits', nil, nil)
            local coded, why = D.codes(changes, state.codes and state.codes(), log)
            if not coded then
                for _, c in ipairs(changes) do G.free(c.plain) end
                error(why)
            end
            local writes = {}
            Library.report('Encrypting and verifying mod files', 0, #changes)
            for k, c in ipairs(changes) do
                local sealed, reason = D.build(c, function(text) log(c.name .. ': ' .. text); if not closing then shim.pump() end end)
                if not sealed then
                    for j = k + 1, #changes do G.free(changes[j].plain) end
                    error(c.name .. ': ' .. tostring(reason))
                end
                if sealed ~= originals[c.name] then writes[c.name] = sealed end
                Library.report('Encrypting and verifying mod files', k, #changes)
            end
            return Library.publish(I, writes, physics, V.BASE, map, fp, S, FP)
        end, debug.traceback)
        bar.busy = nil
        attempted = signature()
        if not ok then
            log('Library export failed: ' .. tostring(result))
            say('Export failed. Previous library mod kept. See editor log; use Update library to retry.', WARN)
            return false
        end
        last_built = signature()
        bar.base = state.writes
        log('Library export ready: ' .. result .. ' file(s). No game files changed.')
        say('Export ready. Changes pending deployment in Mod Library.', GOOD)
        return true
    end
    local function install(finish)
        if Library.worker then return build() end
        if finish_requested then return false end
        local ok, reason = xpcall(function()
            if state.flush_config then assert(state.flush_config()) end
            C.flush()
            Library.request(I, finish)
        end, debug.traceback)
        if not ok then
            log('Cannot save library snapshot: ' .. tostring(reason))
            say('Could not save edits. Window kept open; see the editor log.', WARN)
            return false
        end
        last_built, attempted = signature(), signature()
        finish_requested = finish or false
        say(finish and 'Saving to library. This window will close when the mod is ready...' or 'Building library mod in the background...', MUTED)
        return true
    end
    local function restore()
        removal_open, removal_down = true, shim.key_down(0x01)
    end
    local function removal_bounds()
        local s = math.min(1.25, shim.w / 900, shim.h / 620)
        local w, h = 700 * s, 410 * s
        return (shim.w-w)/2, (shim.h-h)/2, w, h, s
    end
    paint_removal = function()
        if not removal_open then return end
        local x,y,w,h,s = removal_bounds()
        shim.flush()
        shim.fill(0,0,shim.w,shim.h,{180,0,0,0})
        shim.fill(x,y,x+w,y+h,{255,24,24,24})
        shim.fill(x,y,x+w,y+4*s,GOLD)
        shim.flush()
        shim.text('Remove editor changes',x+30*s,y+47*s,26*s,GOLD,true)
        shim.text('Keep your saved edits. Choose what reaches the game in Mod Library.',x+30*s,y+80*s,15*s,WHITE)
        local steps = {'Close Helldivers 2.', 'Open Mod Library in ModDiver Laboratory.',
                       'Turn OFF the ModDiverEditor changes mod.',
                       'Use Preview Deployment, then Merge and Install All.'}
        for n,text in ipairs(steps) do
            local at = y+(108+(n-1)*42)*s
            shim.text(tostring(n)..'.',x+34*s,at+19*s,18*s,GOLD,true)
            shim.text(text,x+68*s,at+19*s,17*s,WHITE)
        end
        shim.text('Removing a library entry alone does not restore the game.',x+30*s,y+305*s,15*s,MUTED)
        shim.text('Your editor settings remain saved for the next time you open it.',x+30*s,y+330*s,15*s,MUTED)
        local hover = bar.hover == 'close_removal'
        shim.fill(x+w-166*s,y+h-57*s,x+w-26*s,y+h-18*s,hover and {255,255,235,112} or GOLD)
        shim.flush()
        shim.text('Got it',x+w-119*s,y+h-30*s,17*s,{255,20,20,20},true)
    end
    local function removal_input()
        local x,y,w,h,s = removal_bounds()
        local cx,cy = shim.cursor()
        local hover = cx and cx>=x+w-166*s and cx<x+w-26*s and cy>=y+h-57*s and cy<y+h-18*s
        bar.hover = hover and 'close_removal' or nil
        local down = shim.key_down(0x01)
        if shim.key_down(0x1B) or (not down and removal_down and hover) then removal_open=false end
        removal_down = down
    end
    local next_check = 0
    local last_worker_status
    local function auto_export()
        if state.phase ~= 'ready' then
            if Library.worker and state.status ~= last_worker_status then
                last_worker_status = state.status
                Library.report('Finding and preparing editable stats', nil, nil)
            end
            return
        end
        if Library.worker then
            if not last_built then build() end
            exit_requested = true
            return
        end
        if finish_requested then
            local status = Library.status(I)
            if status and status:find('Library updated',1,true) then
                finish_requested, exit_requested = false, true
                return
            elseif status and status:find('failed',1,true) then
                finish_requested = false
            end
        end
        if clock() < next_check then return end
        next_check = clock() + 0.25
        local current = signature()
        if current ~= last_seen then
            last_seen, changed_at = current, clock()
            bar.message = nil
        end
        if not finish_requested and not removal_open and not shim.key_down(0x01) and current ~= last_built and current ~= attempted and clock() - changed_at >= 2 then install() end
    end
