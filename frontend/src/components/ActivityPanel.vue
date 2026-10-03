<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { call } from "@/api"
import { toast, toastError } from "@/toast"
import { debounce, timeAgo } from "@/utils"

const props = defineProps({ doctype: { type: String, required: true }, docname: { type: String, required: true } })
const activity = ref([])
const filter = ref("all")
const comment = ref("")
const posting = ref(false)
const expanded = ref(new Set())
const tagSuggestions = ref([])
const taggedUsers = ref([])
const tagQuery = computed(() => comment.value.match(/(?:^|\s)@([^\s]*)$/)?.[1] ?? null)
const searchTags = debounce(async () => {
	if (tagQuery.value === null) { tagSuggestions.value = []; return }
	try { tagSuggestions.value = await call("get_comment_tag_users", { doctype: props.doctype, name: props.docname, search: tagQuery.value }) }
	catch (error) { tagSuggestions.value = []; toastError(error) }
}, 220)
watch(comment, searchTags)

function selectTag(user) {
	comment.value = comment.value.replace(/(^|\s)@([^\s]*)$/, `$1@${user} `)
	if (!taggedUsers.value.includes(user)) taggedUsers.value.push(user)
	tagSuggestions.value = []
}

const visible = computed(() => activity.value.filter((row) => filter.value === "all" || row.type === filter.value))
const counts = computed(() => ({
	comment: activity.value.filter((row) => row.type === "comment").length,
	email: activity.value.filter((row) => row.type === "email").length,
	edit: activity.value.filter((row) => row.type === "edit").length,
}))

async function load() {
	activity.value = await call("get_document_activity", { doctype: props.doctype, name: props.docname })
}

async function postComment() {
	if (!comment.value.trim()) return
	posting.value = true
	try {
		await call("add_document_comment", { doctype: props.doctype, name: props.docname,
			content: comment.value.trim().replace(/\n/g, "<br>"), tagged_users: taggedUsers.value.filter((user) => comment.value.includes(`@${user}`)) })
		comment.value = ""
		taggedUsers.value = []
		toast("Comment added")
		await load()
	} catch (error) {
		toastError(error)
	} finally {
		posting.value = false
	}
}

function toggle(name) {
	const next = new Set(expanded.value)
	next.has(name) ? next.delete(name) : next.add(name)
	expanded.value = next
}

defineExpose({ load })
onMounted(load)
</script>

<template>
	<section class="cp-card cp-activity">
		<header class="cp-card-head">
			<h3>Activity</h3>
			<div class="cp-segmented">
				<button :class="{ active: filter === 'all' }" @click="filter = 'all'">All</button>
				<button :class="{ active: filter === 'comment' }" @click="filter = 'comment'">Comments {{ counts.comment || "" }}</button>
				<button :class="{ active: filter === 'email' }" @click="filter = 'email'">Emails {{ counts.email || "" }}</button>
				<button :class="{ active: filter === 'edit' }" @click="filter = 'edit'">Edits {{ counts.edit || "" }}</button>
			</div>
		</header>
		<form class="cp-comment-box" @submit.prevent="postComment">
			<div style="position: relative; flex: 1">
				<textarea v-model="comment" rows="2" class="cp-input" style="width: 100%" placeholder="Add a comment; type @ to tag a Raven user…" @keydown.meta.enter="postComment" @keydown.ctrl.enter="postComment" />
				<div v-if="tagSuggestions.length && tagQuery !== null" class="cp-options" style="position: absolute; z-index: 20; width: 100%; max-height: 180px; overflow: auto">
					<button v-for="user in tagSuggestions" :key="user.user" type="button" @click="selectTag(user.user)"><strong>{{ user.full_name || user.user }}</strong><small>{{ user.user }}</small></button>
				</div>
			</div>
			<button class="cp-btn primary sm" type="submit" :disabled="posting || !comment.trim()">Comment</button>
		</form>
		<ol class="cp-timeline">
			<li v-for="row in visible" :key="row.name" :class="row.type">
				<span class="cp-timeline-dot">
					<svg v-if="row.type === 'email'" viewBox="0 0 24 24"><path d="M4 6h16v12H4zM4 7l8 6 8-6" /></svg>
					<svg v-else viewBox="0 0 24 24"><path d="M5 5h14v10H9l-4 4z" /></svg>
				</span>
				<div class="cp-timeline-body">
					<div class="cp-timeline-meta">
						<strong>{{ row.by }}</strong>
						<span v-if="row.type === 'email'">{{ row.direction === "Received" ? "received an email" : "sent an email" }}</span>
						<span v-else-if="row.type === 'edit'">edited this document</span>
						<span v-else-if="row.type === 'event'">updated its status</span>
						<span v-else>commented</span>
						<time :title="row.creation">{{ timeAgo(row.creation) }}</time>
					</div>
					<template v-if="row.type === 'email'">
						<button class="cp-email-summary" @click="toggle(row.name)">
							<strong>{{ row.subject || "(no subject)" }}</strong>
							<small>To {{ row.recipients }}<template v-if="row.cc"> · Cc {{ row.cc }}</template><template v-if="row.has_attachment"> · 📎</template><template v-if="row.status"> · {{ row.status }}</template></small>
						</button>
						<!-- eslint-disable-next-line vue/no-v-html -- content is sanitised server-side by Communication -->
						<div v-if="expanded.has(row.name)" class="cp-rich" v-html="row.content" />
					</template>
					<ul v-if="row.changes?.length"><li v-for="(change, index) in row.changes" :key="index">{{ change }}</li></ul>
					<!-- eslint-disable-next-line vue/no-v-html -- comment content is sanitised on save -->
					<div v-else class="cp-rich" v-html="row.content" />
				</div>
			</li>
			<li v-if="!visible.length" class="cp-empty-row">No activity yet.</li>
		</ol>
	</section>
</template>
