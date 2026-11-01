<script setup lang="ts">
import {onMounted} from 'vue'
onMounted(()=>document.documentElement.classList.toggle('dark',localStorage.getItem('omni-theme')==='dark'))
</script>
<template><RouterView /></template>
