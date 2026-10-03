<template>
	<nav class="cp-page-tabs" aria-label="Controlled catalog sections">
		<RouterLink to="/catalog" class="cp-page-tab" exact-active-class="active">Catalog</RouterLink>
		<RouterLink to="/catalog/approvals" class="cp-page-tab" active-class="active">Approval requests</RouterLink>
		<RouterLink to="/catalog/prices" class="cp-page-tab" active-class="active">Price requests</RouterLink>
	</nav>
</template>
