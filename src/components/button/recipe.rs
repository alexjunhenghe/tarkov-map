use proa_core::ClassList;

pub const BUTTON_BASE: &str = "inline-flex items-center justify-center border border-[#3de1e8] bg-[#3de1e8] px-5 py-3 font-mono text-xs font-bold uppercase tracking-[0.16em] text-[#0b0b0c] transition hover:bg-transparent hover:text-[#3de1e8]";

pub fn button_classes() -> ClassList<1> {
    ClassList::new().add(BUTTON_BASE)
}
