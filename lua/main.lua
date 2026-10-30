-- 파란색 픽셀 여부를 판정하는 공통 인라인 함수
local function is_blue_pixel(r, g, b)
    return b > 0.4 and b > (r + 0.15) and b > (g + 0.15)
end

-- 1. 연속된 파란색 픽셀 구간을 기준으로 영역을 찾아 크롭하는 그리드 생성 함수
local function get_sign_block_grid(source_img_data, block_size, threshold_ratio)
    local width, height = source_img_data:getDimensions()
    
    -- 전체 이미지에서 파란색 픽셀 이진 그리드 생성
    local raw_grid = {}
    local found_pixels = 0
    for y = 0, height - 1 do
        local row = {}
        for x = 0, width - 1 do
            local r, g, b, _ = source_img_data:getPixel(x, y)
            if is_blue_pixel(r, g, b) then
                row[x + 1] = 1
                found_pixels = found_pixels + 1
            else
                row[x + 1] = 0
            end
        end
        raw_grid[y + 1] = row
    end

    -- 노이즈 필터: 전체 파란 픽셀 수가 너무 적으면 무시
    if found_pixels < 80 then return nil, "Too few blue pixels" end

    -- [조건 1] 가로(너비) 방향으로 연속된 파란색 픽셀이 가장 긴 구간 탐색
    local max_run_w = 0
    local best_x1, best_x2 = 1, width
    for y = 1, height do
        local current_run = 0
        local run_start = 1
        for x = 1, width do
            if raw_grid[y][x] == 1 then
                if current_run == 0 then run_start = x end
                current_run = current_run + 1
            else
                if current_run > max_run_w then
                    max_run_w = current_run
                    best_x1 = run_start
                    best_x2 = x - 1
                end
                current_run = 0
            end
        end
        if current_run > max_run_w then
            max_run_w = current_run
            best_x1 = run_start
            best_x2 = width
        end
    end

    -- [조건 2] 세로(폭) 방향으로 연속된 파란색 픽셀이 가장 긴 구간 탐색
    local max_run_h = 0
    local best_y1, best_y2 = 1, height
    for x = 1, width do
        local current_run = 0
        local run_start = 1
        for y = 1, height do
            if raw_grid[y][x] == 1 then
                if current_run == 0 then run_start = y end
                current_run = current_run + 1
            else
                if current_run > max_run_h then
                    max_run_h = current_run
                    best_y1 = run_start
                    best_y2 = y - 1
                end
                current_run = 0
            end
        end
        if current_run > max_run_h then
            max_run_h = current_run
            best_y1 = run_start
            best_y2 = height
        end
    end

    -- 연속된 픽셀의 크기가 너무 작으면 노이즈로 판단하여 무시
    if max_run_w < 20 or max_run_h < 20 then return nil, "Continuous area too small" end

    -- [조건 3] 표지판이 정사각형/원형이므로, 두 연속 구간 중 최대 길이를 기준으로 정사각형 영역 확정
    local max_side = math.max(max_run_w, max_run_h)
    local center_x = (best_x1 + best_x2) / 2
    local center_y = (best_y1 + best_y2) / 2

    local min_x = math.floor(center_x - max_side / 2)
    local max_x = min_x + max_side - 1
    local min_y = math.floor(center_y - max_side / 2)
    local max_y = min_y + max_side - 1

    -- 이미지 경계 클리핑
    min_x = math.max(1, min_x)
    min_y = math.max(1, min_y)
    max_x = math.min(width, max_x)
    max_y = math.min(height, max_y)

    -- 블록 그리드 생성
    block_size = block_size or 10
    threshold_ratio = threshold_ratio or 0.15

    local crop_w = max_x - min_x + 1
    local crop_h = max_y - min_y + 1
    local grid_w = math.ceil(crop_w / block_size)
    local grid_h = math.ceil(crop_h / block_size)
    local small_grid = {}

    for by = 0, grid_h - 1 do
        local row = {}
        for bx = 0, grid_w - 1 do
            local blue_count = 0
            local total_count = 0

            for py = 0, block_size - 1 do
                for px = 0, block_size - 1 do
                    local cur_x = min_x + (bx * block_size + px) - 1
                    local cur_y = min_y + (by * block_size + py) - 1

                    if cur_x >= 0 and cur_x < width and cur_y >= 0 and cur_y < height then
                        total_count = total_count + 1
                        if raw_grid[cur_y + 1][cur_x + 1] == 1 then
                            blue_count = blue_count + 1
                        end
                    end
                end
            end

            row[bx + 1] = (blue_count > (total_count * threshold_ratio)) and 1 or 0
        end
        small_grid[by + 1] = row
    end

    return small_grid
end

-- 2. 방향 판정 로직 (중앙 기준 좌우 파란 픽셀 수 비교)
local function get_direction(grid)
    if not grid or #grid == 0 then return "unknown" end

    local height = #grid
    local width = #grid[1]
    local mid_x = width / 2

    local left_count = 0
    local right_count = 0

    for y = 1, height do
        for x = 1, width do
            if grid[y][x] == 1 then
                if x <= mid_x then
                    left_count = left_count + 1
                else
                    right_count = right_count + 1
                end
            end
        end
    end

    if left_count > right_count then
        return "left"
    elseif right_count > left_count then
        return "right"
    else
        return "unknown"
    end
end

-- 3. 콘솔 그리드 출력 함수 (디버깅용)
local function print_grid(grid)
    if not grid then return end
    print(string.format("--- Grid Dimensions: %d rows x %d cols ---", #grid, #grid[1]))
    for y = 1, #grid do
        local line = ""
        for x = 1, #grid[y] do
            line = line .. (grid[y][x] == 1 and "1 " or ". ")
        end
        print(line)
    end
end

-- =====================================================================
-- IP 카메라 연동 및 실시간 반복 실행 영역
-- =====================================================================
local timer = 0
local interval = 0.25 -- 0.25초마다 이미지 갱신 및 방향 분석

function love.update(dt)
    timer = timer + dt
    if timer >= interval then
        timer = 0
        
        local success, img_data = pcall(love.image.newImageData, "current.jpg")
        
        if success and img_data then
            local grid = get_sign_block_grid(img_data, 1)
            
            if grid then
                --print_grid(grid) -- 디버깅 필요시 주석 해제
                local direction = get_direction(grid)
                print(direction)
            end
        else
            print("unknown")
        end
    end
end