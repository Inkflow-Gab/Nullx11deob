-- null • RoMidi Clyde loader recovery
-- Derived statically from the attached file; the recovered code was NOT executed.
-- This is the loader only. The external MIDI payload is NOT included or fetched.
-- Clyde engine upstream: JamiesNolandGiggleShi1er/ClydeDeobfuscator (MIT).
-- Sample-scoped register-VM refinement: null. Behavior equivalence is not certified.

local compile = loadstring
local service = game
local httpGet = service["HttpGet"]
local entrypoint = compile(httpGet(service, "https://gist.githubusercontent.com/wownskdo/2702d7700c9eafc0e9b4a4b192ba3913/raw/yes"))
entrypoint()
return
