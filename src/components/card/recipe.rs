use proa_core::ClassList;

pub const CARD_BASE: &str = "border border-white/20 bg-white/[0.035] p-6";

pub fn card_classes() -> ClassList<1> {
    ClassList::new().add(CARD_BASE)
}
