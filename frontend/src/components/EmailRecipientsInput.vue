<script setup>
import { ref, watch } from "vue"
import { call } from "@/api"
import { debounce } from "@/utils"
import { useFloatingPanel } from "@/floating"

const props = defineProps({
	modelValue: { type: String, default: "" },
	label: { type: String, default: "" },
	placeholder: { type: String, default: "" },
	required: { type: Boolean, default: false },
})
const emit = defineEmits(["update:modelValue"])
const query = ref(props.modelValue || "")
const options = ref([])
const open = ref(false)
const highlighted = ref(0)
const anchor = ref(null)
const { style: panelStyle, place } = useFloatingPanel(anchor, open)

function currentToken(value) {
	const parts = String(value || "").split(",")
	return (parts[parts.length - 1] || "").trim()
}

function applyEmail(email) {
	const parts = String(query.value || "").split(",")
	parts[parts.length - 1] = ` ${email}`
	const next = parts.map((part) => part.trim()).filter(Boolean).join(", ")
	query.value = next
	emit("update:modelValue", next)
	options.value = []
	open.value = false
}

const search = debounce(async () => {
	const token = currentToken(query.value)
	if (token.length < 1) {
		options.value = []
		return
	}
	try {
		options.value = await call("search_user_emails", { txt: token })
		highlighted.value = 0
		place()
	} catch {
		options.value = []
	}
}, 200)

function onFocus() {
	open.value = true
	search()
}

function onInput() {
	open.value = true
	emit("update:modelValue", query.value)
	search()
}

function select(option) {
	applyEmail(option.email)
}

function onBlur() {
	setTimeout(() => {
		open.value = false
		if (query.value !== props.modelValue) query.value = props.modelValue || ""
	}, 150)
}

function onKey(event) {
	if (!open.value || !options.value.length) return
	if (event.key === "ArrowDown") highlighted.value = Math.min(highlighted.value + 1, options.value.length - 1)
	else if (event.key === "ArrowUp") highlighted.value = Math.max(highlighted.value - 1, 0)
	else if (event.key === "Enter") {
		select(options.value[highlighted.value])
		event.preventDefault()
	}
	else return
	event.preventDefault()
}

watch(() => props.modelValue, (value) => { query.value = value || "" })
</script>

<template>
	<label class="cp-field">
		<span v-if="label">{{ label }}<i v-if="required">*</i></span>
		<div ref="anchor" class="cp-combo">
			<input
				v-model="query"
				class="cp-input"
				:placeholder="placeholder"
				:required="required"
				autocomplete="off"
				@focus="onFocus"
				@input="onInput"
				@blur="onBlur"
				@keydown="onKey"
			/>
			<Teleport to="body">
				<div v-if="open && options.length" class="cp-options cp-floating" :style="panelStyle">
					<button
						v-for="(option, index) in options"
						:key="option.email"
						type="button"
						:class="{ highlighted: index === highlighted }"
						@mousedown.prevent="select(option)"
					>
						<strong>{{ option.full_name }}</strong>
						<small>{{ option.email }}</small>
					</button>
				</div>
			</Teleport>
		</div>
	</label>
</template>
