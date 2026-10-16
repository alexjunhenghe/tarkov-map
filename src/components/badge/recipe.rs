use proa_core::ClassList;

pub const BADGE_BASE: &str = "inline-flex items-center border border-current px-2 py-1 font-mono text-[10px] uppercase tracking-[0.18em]";

pub fn badge_classes() -> ClassList<1> {
    ClassList::new().add(BADGE_BASE)
}
