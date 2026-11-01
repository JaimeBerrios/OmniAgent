export const initials = (name: string) => name.split(/[ @]+/).filter(Boolean).slice(0,2).map(x=>x[0]).join('').toUpperCase()
export const date = (value: string) => new Intl.DateTimeFormat('es-SV', {day:'2-digit', month:'short', year:'numeric'}).format(new Date(value))
export const time = (value: string) => new Intl.DateTimeFormat('es-SV', {hour:'2-digit', minute:'2-digit'}).format(new Date(value))
