extends Control
## Original code-drawn prototype artwork; no external raster assets.
var growth_stage := 0
var planted := false
var wilted := false
var splash := 0.0
var phase := 0.0

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE

func _process(delta: float) -> void:
	phase += delta
	splash = maxf(0.0, splash - delta)
	queue_redraw()

func ellipse(center: Vector2, radius: Vector2, color: Color, angle: float = 0.0) -> void:
	var points := PackedVector2Array()
	for i in range(40):
		var a := TAU * float(i) / 40.0
		points.append(center + Vector2(cos(a) * radius.x, sin(a) * radius.y).rotated(angle))
	draw_colored_polygon(points, color)

func _draw() -> void:
	var w := size.x
	var h := size.y
	var center := Vector2(w * 0.5, h * 0.80)
	var room := Rect2(w * .23, 0, w * .54, h * .88)
	var arch := StyleBoxFlat.new()
	arch.bg_color = Color("e7eee2")
	arch.corner_radius_top_left = 80
	arch.corner_radius_top_right = 80
	draw_style_box(arch, room)
	draw_circle(Vector2(w * .65, h * .22), 15, Color("f5dfa1"))
	draw_line(Vector2(w * .5, 8), Vector2(w * .5, h * .76), Color("f5f6ed"), 3)
	draw_line(Vector2(w * .24, h * .4), Vector2(w * .76, h * .4), Color("f5f6ed"), 3)
	draw_line(Vector2(w * .17, h * .89), Vector2(w * .83, h * .89), Color("c6b79e"), 4)
	ellipse(center + Vector2(0, 18), Vector2(57, 8), Color(0.2, .25, .15, .09))
	var sway := sin(phase * 1.4) * 2.0
	var green := Color("698a5b") if not wilted else Color("a99571")
	if planted and growth_stage > 0:
		var stem_height := 28.0 + growth_stage * 16.0
		var head := center + Vector2(sway, -stem_height)
		if wilted: head += Vector2(16, 17)
		draw_polyline(PackedVector2Array([center, center + Vector2(-4, -stem_height * .45), head]), green, 4, true)
		ellipse(center + Vector2(-14, -stem_height * .4), Vector2(19, 7), green, .45)
		if growth_stage >= 2:
			ellipse(center + Vector2(14, -stem_height * .63), Vector2(20, 8), green, -.5)
		if growth_stage == 3:
			ellipse(head, Vector2(10, 14), Color("ede1bd"))
		elif growth_stage == 4:
			for i in range(11):
				var a := TAU * float(i) / 11.0 + sway * .02
				ellipse(head + Vector2(cos(a), sin(a)) * 17, Vector2(15, 7), Color("fffbed"), a)
			draw_circle(head, 11, Color("d4a53c"))
			draw_circle(head + Vector2(-3, -3), 3, Color("e8c369"))
	var pot := PackedVector2Array([center + Vector2(-38, -6), center + Vector2(38, -6), center + Vector2(29, 29), center + Vector2(-29, 29)])
	draw_colored_polygon(pot, Color("c08062"))
	draw_rect(Rect2(center + Vector2(-41, -10), Vector2(82, 12)), Color("d49a79"))
	ellipse(center + Vector2(0, -10), Vector2(37, 5), Color("785943"))
	if planted and growth_stage == 0:
		ellipse(center + Vector2(0, -13), Vector2(6, 3), Color("d4bb85"), -.4)
	if splash > 0:
		for i in range(7):
			var x := center.x - 31 + i * 10
			var y := center.y - 30 - fmod((1.0 - splash) * 70 + i * 12, 65)
			draw_line(Vector2(x, y), Vector2(x - 2, y + 7), Color(.43, .66, .78, splash), 2, true)
