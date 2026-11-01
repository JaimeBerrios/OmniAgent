<script setup lang="ts">import {Info} from 'lucide-vue-next';defineProps<{error?:boolean}>()</script>
<template><div class="notice" :class="{error}" :role="error?'alert':'status'"><Info :size="17"/><span><slot/></span></div></template>
