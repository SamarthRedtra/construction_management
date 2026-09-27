import { onBeforeUnmount, ref, watch } from "vue"

// Places a dropdown panel under (or above) its input with position: fixed, so the panel can be
// teleported to <body> and never clipped by a scrolling card, table or modal.
export function useFloatingPanel(anchor, open) {
	const style = ref({})

	function place() {
		if (!anchor.value) return
		const rect = anchor.value.getBoundingClientRect()
		const spaceBelow = window.innerHeight - rect.bottom
		const openUp = spaceBelow < 240 && rect.top > spaceBelow
		const room = (openUp ? rect.top : spaceBelow) - 12
		style.value = {
			left: `${rect.left}px`,
			width: `${Math.max(rect.width, 260)}px`,
			maxHeight: `${Math.max(Math.min(280, room), 120)}px`,
			...(openUp ? { bottom: `${window.innerHeight - rect.top + 4}px` } : { top: `${rect.bottom + 4}px` }),
		}
	}

	function stop() {
		window.removeEventListener("scroll", place, true)
		window.removeEventListener("resize", place)
	}

	watch(open, (isOpen) => {
		stop()
		if (!isOpen) return
		place()
		window.addEventListener("scroll", place, true)
		window.addEventListener("resize", place)
	})
	onBeforeUnmount(stop)

	return { style, place }
}
