-- Original null fixture: known semantics, not a protected customer script.
return {
    anonymous = function(state, code, constants, constants)
        return function(upvalues, unused)
            return function(...)
                local registers = upvalues
                local pc = 1
                while true do
                    local opcode = code[pc]
                    local low = opcode < 1
                    if low then
                        registers[1] = constants[pc]
                        pc += 1
                    elseif opcode == 1 then
                        return registers[1]
                    else
                        error("invalid synthetic opcode")
                    end
                end
            end
        end
    end,
    named = function(state, code, constants)
        local function bind(upvalues, unused)
            local function execute(...)
                local registers = upvalues
                local pc = 1
                local result = pcall(function(...)
                    while true do
                        local opcode = code[pc]
                        if opcode == 0 then
                            registers[1] = constants[pc]
                            pc += 1
                        else
                            return registers[1]
                        end
                    end
                end)
                return result
            end
            return execute
        end
        return bind
    end,
    -- A merge loop in application code must NOT become a VM merely because
    -- its second RHS indexes an array (a false positive in the public mapper).
    application = function(values, indexes)
        local i = 1
        while true do
            local a, b = values[i] or nil, indexes[i]
            if a then i += 1 elseif b then i += 1 else break end
        end
    end,
}
