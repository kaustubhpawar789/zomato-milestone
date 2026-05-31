document.addEventListener('DOMContentLoaded', () => {
    
    // --- Premium Food Images (Curated from Unsplash for "Wow" factor) ---
    const premiumImages = [
        "https://images.unsplash.com/photo-1555396273-367ea4eb4db5?q=80&w=800&auto=format&fit=crop", // Restaurant interior
        "https://images.unsplash.com/photo-1504674900247-0877df9cc836?q=80&w=800&auto=format&fit=crop", // Fine dining plating
        "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?q=80&w=800&auto=format&fit=crop", // Ambient dining
        "https://images.unsplash.com/photo-1544148103-0773bf10d330?q=80&w=800&auto=format&fit=crop", // Gourmet burger
        "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?q=80&w=800&auto=format&fit=crop", // Fine dining chef
        "https://images.unsplash.com/photo-1552566626-52f8b828add9?q=80&w=800&auto=format&fit=crop", // Premium sushi
        "https://images.unsplash.com/photo-1550966871-3ed3cdb5ed0c?q=80&w=800&auto=format&fit=crop", // Pasta
        "https://images.unsplash.com/photo-1579027989536-b7b1f875659b?q=80&w=800&auto=format&fit=crop", // Modern asian
        "https://images.unsplash.com/photo-1514933651103-005eec06c04b?q=80&w=800&auto=format&fit=crop", // Cocktails / Bar
        "https://images.unsplash.com/photo-1565299624946-b28f40a0ae38?q=80&w=800&auto=format&fit=crop"  // Pizza
    ];

    // --- State ---
    let state = {
        location: 'Bangalore',
        budget: 'medium',
        rating: 3.5,
        cuisine: ''
    };
    let allLocations = [];
    let activeFilter = null;

    // --- DOM Elements ---
    const sheet = document.getElementById('filter-sheet');
    const backdrop = document.getElementById('modal-backdrop');
    const closeSheetBtn = document.getElementById('close-sheet');
    const btnApply = document.getElementById('btn-apply-filter');
    const sheetTitle = document.getElementById('sheet-title');
    
    const contentDivs = {
        location: document.getElementById('content-location'),
        budget: document.getElementById('content-budget'),
        rating: document.getElementById('content-rating'),
        cuisine: document.getElementById('content-cuisine')
    };

    const pillLabels = {
        location: document.getElementById('label-location'),
        budget: document.getElementById('label-budget'),
        rating: document.getElementById('label-rating'),
        cuisine: document.getElementById('label-cuisine')
    };

    // --- Init Data ---
    fetch('/api/locations')
        .then(res => res.json())
        .then(data => {
            allLocations = data.locations;
            if(allLocations.includes('Bangalore')) {
                state.location = 'Bangalore';
            } else if (allLocations.length > 0) {
                state.location = allLocations[0];
            }
            pillLabels.location.textContent = state.location;
            renderLocationList(allLocations);
        })
        .catch(err => console.error("Failed to load locations", err));

    // --- Sheet Logic (Premium Slide & Blur) ---
    function openSheet(type, title) {
        activeFilter = type;
        sheetTitle.textContent = title;
        
        Object.values(contentDivs).forEach(div => div.classList.add('hidden'));
        contentDivs[type].classList.remove('hidden');
        contentDivs[type].classList.add('flex');

        backdrop.classList.remove('hidden');
        void backdrop.offsetWidth; // Force reflow
        backdrop.classList.remove('opacity-0');
        backdrop.classList.add('opacity-100');
        
        sheet.classList.remove('translate-y-full');
        sheet.classList.remove('md:scale-95', 'md:opacity-0');
    }

    function closeSheet() {
        sheet.classList.add('translate-y-full', 'md:scale-95');
        backdrop.classList.remove('opacity-100');
        backdrop.classList.add('opacity-0');
        setTimeout(() => {
            backdrop.classList.add('hidden');
            activeFilter = null;
        }, 300);
    }

    backdrop.addEventListener('click', closeSheet);
    closeSheetBtn.addEventListener('click', closeSheet);

    // --- Pills Click ---
    document.getElementById('btn-location').addEventListener('click', () => openSheet('location', 'Select Location'));
    document.getElementById('btn-budget').addEventListener('click', () => openSheet('budget', 'Select Budget'));
    document.getElementById('btn-rating').addEventListener('click', () => openSheet('rating', 'Minimum Rating'));
    document.getElementById('btn-cuisine').addEventListener('click', () => openSheet('cuisine', 'Cuisine'));

    // --- Sheet Interactions ---
    // Location
    const locSearch = document.getElementById('loc-search');
    const locList = document.getElementById('loc-list');
    
    function renderLocationList(list) {
        locList.innerHTML = '';
        list.forEach(loc => {
            const div = document.createElement('div');
            const isActive = state.location === loc;
            div.className = `p-4 rounded-2xl cursor-pointer transition-all ${isActive ? 'bg-zomato-red/10 border-l-4 border-zomato-red text-white font-bold' : 'hover:bg-white/5 border-l-4 border-transparent text-text-primary'}`;
            div.textContent = loc;
            div.addEventListener('click', () => {
                state.location = loc;
                renderLocationList(list);
                applyPreferences(); // Auto-apply
            });
            locList.appendChild(div);
        });
    }

    locSearch.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase();
        const filtered = allLocations.filter(l => l.toLowerCase().includes(query));
        renderLocationList(filtered);
    });

    // Budget
    const budgetLabels = document.querySelectorAll('#content-budget label');
    budgetLabels.forEach(label => {
        label.addEventListener('click', () => {
            budgetLabels.forEach(l => {
                l.classList.remove('bg-zomato-red/10', 'border-zomato-red');
                l.classList.add('border-white/10');
                
                const iconContainer = l.querySelector('.w-10');
                iconContainer.classList.remove('bg-zomato-red/20', 'text-zomato-lightRed');
                iconContainer.classList.add('bg-white/5', 'text-white/60');
                
                const circle = l.querySelector('.check-circle');
                circle.classList.remove('border-zomato-red');
                circle.classList.add('border-white/20');
                circle.innerHTML = '';
            });
            
            label.classList.add('bg-zomato-red/10', 'border-zomato-red');
            label.classList.remove('border-white/10');
            
            const iconContainer = label.querySelector('.w-10');
            iconContainer.classList.add('bg-zomato-red/20', 'text-zomato-lightRed');
            iconContainer.classList.remove('bg-white/5', 'text-white/60');
            
            const circle = label.querySelector('.check-circle');
            circle.classList.add('border-zomato-red');
            circle.classList.remove('border-white/20');
            circle.innerHTML = '<div class="w-3 h-3 bg-zomato-red rounded-full"></div>';
            
            state.budget = label.dataset.budget;
            setTimeout(() => { applyPreferences(); }, 150); // Auto-apply with slight delay for ripple effect
        });
    });

    // Rating
    const ratingInput = document.getElementById('rating-sheet-input');
    const ratingVal = document.getElementById('rating-sheet-val');
    ratingInput.addEventListener('input', (e) => {
        const val = parseFloat(e.target.value).toFixed(1);
        ratingVal.textContent = val;
        state.rating = val;
    });

    // Apply Preferences Logic
    function applyPreferences() {
        pillLabels.location.textContent = state.location;
        let budgetStr = state.budget === 'low' ? 'Accessible' : (state.budget === 'medium' ? 'Moderate' : 'Premium');
        pillLabels.budget.textContent = budgetStr;
        pillLabels.rating.textContent = state.rating + '+ Rating';
        
        const cuisineRaw = document.getElementById('cuisine-sheet-input').value.trim();
        state.cuisine = cuisineRaw;
        pillLabels.cuisine.textContent = cuisineRaw ? cuisineRaw : 'Any Cuisine';
        
        closeSheet();
    }

    // Apply Button (for manual apply, e.g., after typing cuisine or using rating slider)
    btnApply.addEventListener('click', applyPreferences);

    // --- Recommendation Fetching ---
    const btnSearch = document.getElementById('btn-search');
    const emptyState = document.getElementById('empty-state');
    const loadingState = document.getElementById('loading-state');
    const resultsState = document.getElementById('results-state');
    const resultsContainer = document.getElementById('results-container');
    const hintsContainer = document.getElementById('hints-container');
    const aiSummaryContainer = document.getElementById('ai-summary-container');
    const aiSummaryText = document.getElementById('ai-summary-text');
    const mainScroll = document.getElementById('main-scroll');

    btnSearch.addEventListener('click', async () => {
        // UI Transitions
        emptyState.classList.add('hidden');
        resultsState.classList.add('hidden');
        resultsState.classList.remove('flex');
        
        loadingState.classList.remove('hidden');
        loadingState.classList.add('flex');
        
        // Scroll to top
        mainScroll.scrollTo({ top: 0, behavior: 'smooth' });
        
        const payload = {
            location: state.location,
            budget: state.budget,
            cuisine: state.cuisine || null,
            min_rating: parseFloat(state.rating)
        };

        try {
            const res = await fetch('/api/recommend', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            
            // Artificial delay to show off the premium skeleton (min 1.2s)
            setTimeout(() => {
                renderResults(data);
            }, 1200);
            
        } catch(err) {
            console.error(err);
            alert("Error fetching recommendations.");
            loadingState.classList.remove('flex');
            loadingState.classList.add('hidden');
            emptyState.classList.remove('hidden');
        }
    });

    function renderResults(data) {
        loadingState.classList.remove('flex');
        loadingState.classList.add('hidden');
        
        resultsState.classList.remove('hidden');
        resultsState.classList.add('flex');
        
        resultsContainer.innerHTML = '';
        
        if(data.recommendations && data.recommendations.length > 0) {
            hintsContainer.classList.add('hidden');
            aiSummaryContainer.classList.remove('hidden');
            aiSummaryText.textContent = data.summary;
            
            data.recommendations.forEach((rec, idx) => {
                const r = rec.restaurant;
                
                // Determine Rating Color
                let ratingClass = 'rating-average';
                if(r.rating >= 4.0) ratingClass = 'rating-excellent';
                else if(r.rating >= 3.5) ratingClass = 'rating-good';

                // Pick a premium image based on index
                const imgUrl = premiumImages[idx % premiumImages.length];

                const card = document.createElement('div');
                card.className = "stagger-item premium-card glass-panel rounded-3xl overflow-hidden shadow-glass transform transition-all duration-300 flex flex-col h-full";
                card.style.animationDelay = `${idx * 0.15}s`;

                card.innerHTML = `
                    <div class="h-[220px] w-full relative card-img-container bg-black shrink-0">
                        <img src="${imgUrl}" alt="${r.name}" class="w-full h-full object-cover opacity-80" />
                        <div class="absolute inset-0 bg-gradient-to-t from-[#18181b] via-transparent to-transparent"></div>
                        
                        <div class="absolute top-4 left-4 w-10 h-10 rounded-full bg-black/40 backdrop-blur-md flex items-center justify-center text-white font-display font-bold text-lg border border-white/20 shadow-lg">
                            #${idx + 1}
                        </div>
                        
                        <div class="absolute top-4 right-4 px-3 py-1.5 rounded-xl ${ratingClass} font-bold text-sm flex items-center gap-1 shadow-lg backdrop-blur-sm border border-white/20">
                            ${r.rating} <span class="material-symbols-outlined text-[14px]">star</span>
                        </div>
                    </div>
                    
                    <div class="p-6 flex flex-col flex-1 relative bg-black/40">
                        <!-- Floating Cost Badge -->
                        <div class="absolute -top-6 right-6 bg-zomato-red text-white px-4 py-1.5 rounded-full text-sm font-display font-bold shadow-[0_4px_15px_rgba(226,55,68,0.5)] border border-zomato-lightRed/50">
                            ₹${r.cost} <span class="text-white/70 font-normal text-xs">/two</span>
                        </div>
                        
                        <h2 class="font-display text-2xl font-bold text-white mb-1 leading-tight">${r.name}</h2>
                        
                        <div class="flex items-center gap-1.5 text-text-secondary text-sm mb-4">
                            <span class="material-symbols-outlined text-[16px]">location_on</span>
                            ${r.location}
                        </div>
                        
                        <div class="flex flex-wrap gap-2 mb-6">
                            ${r.cuisines.split(',').map(c => `<span class="bg-white/5 text-text-primary px-3 py-1 rounded-full text-xs border border-white/10 shadow-sm">${c.trim()}</span>`).join('')}
                        </div>
                        
                        <div class="mt-auto bg-black/30 rounded-2xl p-4 border border-white/5 border-l-2 border-l-zomato-lightRed">
                            <div class="flex items-center gap-1.5 text-zomato-lightRed font-display font-bold text-sm mb-1.5">
                                <span class="material-symbols-outlined text-[18px]">psychology</span>
                                Why it fits
                            </div>
                            <p class="text-text-secondary text-sm leading-relaxed">${rec.explanation}</p>
                        </div>
                    </div>
                `;
                resultsContainer.appendChild(card);
            });
        } else {
            // Empty results
            aiSummaryContainer.classList.add('hidden');
            hintsContainer.classList.remove('hidden');
            hintsContainer.classList.add('flex');
            
            const hintText = (data.metadata.hints || []).join(' or ');
            document.getElementById('hints-text').textContent = data.summary + (hintText ? ` Hint: ${hintText}` : '');
        }
    }
});
