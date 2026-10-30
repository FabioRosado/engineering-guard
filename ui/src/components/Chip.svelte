<script>
  let { name, verdict } = $props();
</script>

<span class="chip {verdict}" title="{name}: {verdict}">{name}</span>
