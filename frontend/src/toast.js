import { reactive } from "vue"

export const toasts = reactive([])
let nextId = 1

export function toast(message, tone = "success") {
	const id = nextId++
	toasts.push({ id, message, tone })
	setTimeout(() => {
		const index = toasts.findIndex((item) => item.id === id)
		if (index >= 0) toasts.splice(index, 1)
	}, tone === "error" ? 7000 : 3500)
}

export function toastError(error) {
	toast(error?.message || String(error), "error")
}
