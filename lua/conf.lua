function love.conf(t)
    t.console = true -- Windows에서 콘솔 창 강제 활성화
    
    t.modules.window = false
    t.modules.graphics = false

    t.modules.image = true
    t.modules.filesystem = true
    t.modules.event = true
end