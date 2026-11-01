<script setup lang="ts">import {initials} from '../utils/format';defineProps<{name:string;index?:number}>()</script>
<template><span class="avatar" :class="'avatar-'+((index||0)%4)">{{initials(name)}}</span></template>
