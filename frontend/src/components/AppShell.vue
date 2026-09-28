<script setup>
import { computed, ref, watch } from "vue"
import { useRoute } from "vue-router"
import { call, request } from "@/api"
import { toast, toastError } from "@/toast"
import { session } from "@/utils"

const LOGO = "/assets/construction_management/images/controlled-procurement.svg"
const route = useRoute()
const sidebarOpen = ref(false)
const menuOpen = ref(false)
const companyOpen = ref(false)
const switching = ref(false)
const context = computed(() => session.context)

const nav = computed(() => {
	const ctx = context.value
	const counts = ctx.dashboard || {}
	return [
		{ to: "/dashboard", label: "Overview", icon: "grid", visible: true },
		{ to: "/open-lpos", label: "Open LPOs", icon: "clock", visible: ctx.can_purchase, count: counts.open_lpos },
		{ to: "/purchase-orders", label: "Purchase Orders", icon: "cart", visible: ctx.can_purchase },
		{ to: "/receipts", label: "Receive Notes", icon: "inbox", visible: ctx.can_purchase },
		{ to: "/invoices", label: "Purchase Invoices", icon: "invoice", visible: ctx.can_purchase, count: counts.unpaid_invoices },
		{ to: "/transfers", label: "Material Transfers", icon: "swap", visible: ctx.can_transfer },
		{ to: "/catalog", label: "Controlled Catalog", icon: "book", visible: true },
	].filter((item) => item.visible)
})

const initials = computed(() =>
	(context.value.full_name || context.value.user || "U")
		.split(" ")
		.map((part) => part[0])
		.slice(0, 2)
		.join("")
		.toUpperCase(),
)

function isActive(item) {
	return route.path === item.to || route.path.startsWith(`${item.to}/`)
}

async function switchCompany(company) {
	companyOpen.value = false
	if (company === context.value.default_company) return
	switching.value = true
	try {
		session.context = await call("set_active_company", { company })
		session.version++
		toast(`Switched to ${company}`)
	} catch (error) {
		toastError(error)
	} finally {
		switching.value = false
	}
}

async function logout() {
	try {
		await request("logout", {}, "POST")
	} finally {
		window.location.href = "/login"
	}
}

watch(() => route.fullPath, () => {
	sidebarOpen.value = false
	menuOpen.value = false
	companyOpen.value = false
})

const ICONS = {
	grid: "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z",
	clock: "M12 7v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z",
	cart: "M3 4h2l2.4 11h11.2L21 8H6.2M9 20a1 1 0 1 0 0-2 1 1 0 0 0 0 2zm9 0a1 1 0 1 0 0-2 1 1 0 0 0 0 2z",
	inbox: "M4 13h4l2 3h4l2-3h4M4 13l2-8h12l2 8v6H4z",
	invoice: "M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6M9 16h3",
	swap: "M7 7h13l-4-4M17 17H4l4 4",
	book: "M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3zM5 17a3 3 0 0 1 3-3h11",
}
</script>

<template>
	<div class="cp-shell">
		<div v-if="sidebarOpen" class="cp-scrim" @click="sidebarOpen = false" />
		<aside class="cp-sidebar" :class="{ open: sidebarOpen }">
			<div class="cp-brand-wrap">
				<button class="cp-brand" @click="menuOpen = !menuOpen">
					<img :src="LOGO" alt="" />
					<span>Procurement</span>
					<svg viewBox="0 0 24 24" class="cp-chevron"><path d="m6 9 6 6 6-6" /></svg>
				</button>
				<div v-if="menuOpen" class="cp-menu">
					<a href="/desk">Go to Desk</a>
					<a href="/apps">All Apps</a>
					<button @click="logout">Log out</button>
				</div>
			</div>
			<nav class="cp-side-nav">
				<p class="cp-side-label">Controlled Procurement</p>
				<RouterLink v-for="item in nav" :key="item.to" :to="item.to" class="cp-side-link" :class="{ active: isActive(item) }">
					<svg viewBox="0 0 24 24"><path :d="ICONS[item.icon]" /></svg>
					<span>{{ item.label }}</span>
					<em v-if="item.count">{{ item.count }}</em>
				</RouterLink>
			</nav>
			<div class="cp-profile">
				<img v-if="context.user_image" :src="context.user_image" alt="" class="cp-avatar" />
				<span v-else class="cp-avatar">{{ initials }}</span>
				<div>
					<strong>{{ context.full_name || context.user }}</strong>
					<small>{{ context.can_manage_catalog ? "Administrator" : context.can_purchase ? "Purchase" : "Stock" }}</small>
				</div>
			</div>
		</aside>
		<div class="cp-main">
			<header class="cp-topbar">
				<button class="cp-hamburger" aria-label="Open menu" @click="sidebarOpen = true">
					<svg viewBox="0 0 24 24"><path d="M4 6h16M4 12h16M4 18h16" /></svg>
				</button>
				<div class="cp-topbar-spacer" />
				<a class="cp-icon-button" href="/desk" title="Open Desk">
					<svg viewBox="0 0 24 24"><path d="M4 5h16v11H4zM9 20h6M12 16v4" /></svg>
				</a>
				<div v-if="context.companies?.length > 1" class="cp-company-switcher">
					<button class="cp-company" :disabled="switching" @click="companyOpen = !companyOpen">
						<i />{{ context.default_company || "Select company" }}
						<svg viewBox="0 0 24 24" class="cp-chevron"><path d="m6 9 6 6 6-6" /></svg>
					</button>
					<div v-if="companyOpen" class="cp-scrim-clear" @click="companyOpen = false" />
					<div v-if="companyOpen" class="cp-menu cp-company-menu">
						<p class="cp-side-label">Switch company</p>
						<button v-for="company in context.companies" :key="company" :class="{ active: company === context.default_company }" @click="switchCompany(company)">
							<span>{{ company }}</span>
							<svg v-if="company === context.default_company" viewBox="0 0 24 24"><path d="m5 12 5 5 9-10" /></svg>
						</button>
					</div>
				</div>
				<span v-else-if="context.default_company" class="cp-company"><i />{{ context.default_company }}</span>
			</header>
			<main class="cp-content">
				<slot />
			</main>
		</div>
	</div>
</template>
