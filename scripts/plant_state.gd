extends RefCounted
## Deterministic, UI-independent state. All timestamps use Unix seconds (UTC).
const DAY := 86400.0
const WATER_INTERVAL := 2.0 * DAY
const GRACE := DAY
const OFFLINE_CAP := 3.0 * DAY
const NORMAL_DURATION := DAY
const TUTORIAL_DURATION := 60.0
const STAGES := ["씨앗", "새싹", "자라는 중", "봉오리", "활짝 핀 데이지"]

var data: Dictionary

func _init(now: float = 0.0) -> void:
	data = {"schema": 1, "last_update": now, "planted": false,
		"growth": 0.0, "duration": NORMAL_DURATION, "water_due": now,
		"mist_due": now, "tutorial_used": false, "coins": 120,
		"seeds": 1, "collection": [], "vacation": false,
		"settings": {"opacity": 1.0, "topmost": true, "x": -99999, "y": -99999}}

func advance(now: float) -> float:
	var previous := float(data.last_update)
	if now <= previous:
		return 0.0 # Never lower the watermark when the system clock rolls back.
	var elapsed := now - previous
	data.last_update = now
	if data.vacation:
		data.water_due += elapsed
		data.mist_due += elapsed
		return 0.0
	var simulated := minf(elapsed, OFFLINE_CAP)
	var wilt_at := minf(float(data.water_due), float(data.mist_due)) + GRACE
	var healthy_seconds := maxf(0.0, minf(previous + simulated, wilt_at) - previous)
	var before := float(data.growth)
	if data.planted and not is_bloomed():
		data.growth = minf(float(data.duration), before + healthy_seconds)
	# Beyond the cap, both growth and care timers are frozen.
	data.water_due += elapsed - simulated
	data.mist_due += elapsed - simulated
	return float(data.growth) - before

func plant(now: float) -> bool:
	advance(now)
	if data.planted or data.vacation:
		return false
	if int(data.seeds) > 0:
		data.seeds -= 1
	elif int(data.coins) >= 20:
		data.coins -= 20
	else:
		return false
	data.planted = true
	data.growth = 0.0
	data.duration = TUTORIAL_DURATION if not data.tutorial_used else NORMAL_DURATION
	data.tutorial_used = true
	data.water_due = float(data.last_update) + WATER_INTERVAL
	data.mist_due = float(data.last_update) + WATER_INTERVAL
	return true

func care(kind: String, now: float) -> bool:
	advance(now)
	if not data.planted or is_bloomed() or data.vacation or kind not in ["water", "mist"]:
		return false
	var key := "water_due" if kind == "water" else "mist_due"
	# Early care is cosmetic; repeated clicks never increase growth or extend timers.
	if float(data[key]) - float(data.last_update) <= 12.0 * 3600.0:
		data[key] = float(data.last_update) + WATER_INTERVAL
	return true

func harvest(now: float) -> bool:
	advance(now)
	if not is_bloomed():
		return false
	data.collection.append({"id": str(Time.get_ticks_usec()) + "-" + str(randi()),
		"species": "daisy", "harvested_at": float(data.last_update)})
	# Award the second tutorial seed only once, on the tutorial plant's harvest.
	if float(data.duration) == TUTORIAL_DURATION:
		data.seeds += 1
	data.planted = false
	data.growth = 0.0
	return true

func sell_one() -> bool:
	if data.collection.is_empty():
		return false
	data.collection.pop_back()
	data.coins += 50
	return true

func set_vacation(enabled: bool, now: float) -> void:
	advance(now)
	data.vacation = enabled

func is_bloomed() -> bool:
	return data.planted and float(data.growth) >= float(data.duration)

func ratio() -> float:
	return clampf(float(data.growth) / float(data.duration), 0.0, 1.0) if data.planted else 0.0

func stage() -> int:
	var r := ratio()
	if r >= 1.0: return 4
	if r >= 0.70: return 3
	if r >= 0.35: return 2
	if r >= 0.10: return 1
	return 0

func health() -> String:
	if data.vacation: return "휴가 중"
	if not data.planted: return "빈 화분"
	if is_bloomed(): return "개화 완료"
	var late := float(data.last_update) - minf(float(data.water_due), float(data.mist_due))
	if late >= GRACE: return "시듦 · 돌보면 회복돼요"
	if late > 0: return "돌봄이 필요해요"
	return "건강하게 자라고 있어요"

static func valid(candidate: Variant) -> bool:
	if not candidate is Dictionary: return false
	var c: Dictionary = candidate
	for k in ["schema", "last_update", "planted", "growth", "duration", "water_due", "mist_due", "tutorial_used", "coins", "seeds", "collection", "vacation", "settings"]:
		if not c.has(k): return false
	if c.schema != 1: return false
	for k in ["last_update", "growth", "duration", "water_due", "mist_due", "coins", "seeds"]:
		if not (c[k] is float or c[k] is int) or not is_finite(float(c[k])) or float(c[k]) < 0.0:
			return false
	if float(c.duration) <= 0.0 or float(c.growth) > float(c.duration): return false
	if floorf(float(c.coins)) != float(c.coins) or floorf(float(c.seeds)) != float(c.seeds): return false
	for k in ["planted", "tutorial_used", "vacation"]:
		if not c[k] is bool: return false
	if not c.collection is Array or not c.settings is Dictionary: return false
	var ids: Dictionary = {}
	for item in c.collection:
		if not item is Dictionary: return false
		if not item.get("id") is String or item.get("species") != "daisy": return false
		if ids.has(item.id): return false
		ids[item.id] = true
		if not (item.get("harvested_at") is float or item.get("harvested_at") is int): return false
		if not is_finite(float(item.harvested_at)) or float(item.harvested_at) < 0: return false
	var s: Dictionary = c.settings
	if not s.get("topmost") is bool: return false
	for k in ["opacity", "x", "y"]:
		if not (s.get(k) is float or s.get(k) is int) or not is_finite(float(s[k])): return false
	return float(s.opacity) >= 0.1 and float(s.opacity) <= 1.0
